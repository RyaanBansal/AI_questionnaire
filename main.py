from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
import uuid
import os
from dotenv import load_dotenv
import uvicorn
from jose import JWTError, jwt
import requests
from jose import jwk
import datetime

# Imports from your existing files
from models import generate_questions
from database import get_supabase_client, get_supabase_admin_client, verify_jwt

load_dotenv()

SECRET_KEY = os.getenv("SUPABASE_JWT_SECRET")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def create_student_token(email: str, student_id: str):
    """Generates a custom JWT token for a student"""
    payload = {
        "sub": student_id, # Subject is the user ID
        "email": email,
        "role": "student",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

app = FastAPI(title="Admin Assessment API", version="1.2.0")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Verifies token. Checks BOTH 'profiles' (Admins) and 'students' tables.
    """
    payload = verify_jwt(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token structure")

    user_id = payload.get("sub")
    if not user_id: raise HTTPException(status_code=401, detail="Invalid user payload")
    
    admin = get_supabase_admin_client()
    
    # 1. Try finding in 'profiles' (Admin)
    try:
        profile = admin.table('profiles').select('role').eq('id', user_id).single().execute()
        if profile.data:
            return {"id": user_id, "role": profile.data['role'], "email": payload.get("email")}
    except:
        pass # Not a profile, check students next

    # 2. Try finding in 'students' (Student)
    try:
        student = admin.table('students').select('role, full_name, email').eq('id', user_id).single().execute()
        if student.data:
            return {
                "id": user_id, 
                "role": student.data['role'], 
                "email": student.data['email'],
                "full_name": student.data['full_name']
            }
    except:
        pass

    # 3. If neither found
    raise HTTPException(status_code=401, detail="User not found in profiles or students table")

class SignupRequest(BaseModel):
    email: str
    password: str
    role: str # "admin" or "student"

class Token(BaseModel):
    access_token: str
    token_type: str



# --- Pydantic Schemas ---

class DifficultyDistribution(BaseModel):
    Easy: int = Field(..., ge=0, le=100, alias="easy")
    Medium: int = Field(..., ge=0, le=100, alias="medium")
    Hard: int = Field(..., ge=0, le=100, alias="hard")

    @validator('*', always=True)
    def check_sum(cls, v, values):
        if 'Easy' in values and 'Medium' in values and 'Hard' in values:
            total = values['Easy'] + values['Medium'] + values['Hard']
            if total != 100:
                raise ValueError(f"Difficulty distribution must sum to 100%. Current sum: {total}%")
        return v
    
    class Config:
        populate_by_name = True

class TopicConfig(BaseModel):
    topic_name: str = Field(..., alias="topic")
    count: int = Field(..., gt=0)
    difficulty: DifficultyDistribution

# NEW: Module & Client Schemas
class ModuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""

class ClientCreate(BaseModel):
    name: str
    contact_email: Optional[str] = ""
    
class StudentCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    client_id: uuid.UUID
    role: str = "student"
    phone: Optional[str] = None

class AssignModuleRequest(BaseModel):
    module_id: uuid.UUID

# UPDATED: Assessment Schema now accepts an optional Module ID
class AssessmentCreateRequest(BaseModel):
    topics: List[TopicConfig] = Field(..., min_items=1)
    
class AssignAssessmentRequest(BaseModel):
    assessment_id: uuid.UUID

class AssessmentResponse(BaseModel):
    id: uuid.UUID
    topics: List[dict]
    total_questions: int
    message: str
    
# --- Manual Creation Schemas ---
class ManualQuestion(BaseModel):
    question_text: str
    options: List[str] # ["A", "B", "C", "D"]
    correct_answer: str
    difficulty: str # "Easy", "Medium", "Hard"

class ManualAssessmentRequest(BaseModel):
    topic: str
    module_id: Optional[uuid.UUID] = None
    questions: List[ManualQuestion]

class SubmissionRecord(BaseModel):
    id: uuid.UUID
    student_id: str
    score: float
    created_at: str

# --- Helper Functions ---

def create_assessment_record(topics_config: list, total: int, module_id: Optional[uuid.UUID] = None, type: str = "AI") -> uuid.UUID:
    client = get_supabase_admin_client()
    
    # FIX: Create a valid JSON object for difficulty_distribution
    # Since we now have multiple topics with specific difficulties, 
    # we save the list of topics here as well to act as the 'distribution' record.
    
    data = {
        "topic": topics_config, 
        "total_questions": total,
        "difficulty_distribution": topics_config, # Store the topic list here to prevent the NULL error
        "module_id": str(module_id) if module_id else None,
        "type": type
    }
    
    try:
        response = client.table('assessments').insert(data).execute()
        return uuid.UUID(response.data[0]['id'])
    except Exception as e:
        print(f"DB Error creating assessment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create assessment record.")

def save_questions_to_db(assessment_id: uuid.UUID, questions: list[dict]):
    client = get_supabase_admin_client()
    questions_to_insert = []
    for q in questions:
        questions_to_insert.append({
            "assessment_id": str(assessment_id),
            "topic": q.get('topic', 'General'),
            "question_text": q['question_text'],
            "options": q['options'],
            "correct_answer": q['correct_answer'],
            "difficulty": q['difficulty']
        })
    
    try:
        client.table('questions').insert(questions_to_insert).execute()
    except Exception as e:
        print(f"DB Error saving questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to save generated questions.")

# ==========================================
# MODULES & CLIENTS ENDPOINTS
# ==========================================

@app.post("/admin/modules", status_code=201)
async def create_module(module: ModuleCreate):
    client = get_supabase_admin_client()
    try:
        response = client.table('modules').insert(module.dict()).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/modules")
async def get_modules():
    db = get_supabase_admin_client()
    # Fetch modules and their linked assessments
    response = db.table('modules').select("*, assessments(id, topic, total_questions, created_at)").execute()
    return response.data

@app.delete("/admin/modules/{module_id}")
async def delete_module(module_id: str):
    client = get_supabase_admin_client()
    try:
        client.table('modules').delete().eq('id', module_id).execute()
        return {"message": "Module deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/clients", status_code=201)
async def create_client(client: ClientCreate):
    db = get_supabase_admin_client()
    try:
        response = db.table('clients').insert(client.dict()).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/clients")
async def get_clients():
    db = get_supabase_admin_client()
    
    # 1. Fetch the relationships from the 'client_modules' table
    # We join 'clients' and 'modules' to get the full names and details
    try:
        cm_response = db.table('client_modules').select("*, clients(*), modules(*)").execute()
        
        # This returns a list of assignments.
        # Example: [
        #   {client_id: 1, module_id: A, clients: {name: "Acme"}, modules: {name: "Math"}},
        #   {client_id: 1, module_id: B, clients: {name: "Acme"}, modules: {name: "Science"}}
        # ]
        
        # 2. Process this list to group modules under their clients
        clients_dict = {}
        
        for row in cm_response.data:
            client_info = row['clients']
            module_info = row['modules']
            
            client_id = client_info['id']
            
            if client_id not in clients_dict:
                clients_dict[client_id] = {
                    "id": client_info['id'],
                    "name": client_info['name'],
                    "contact_email": client_info.get('contact_email'),
                    "created_at": client_info.get('created_at'),
                    "assigned_modules": [] # List to hold module objects
                }
            
            # Add the module to this client's list
            clients_dict[client_id]['assigned_modules'].append(module_info)
            
        # Return the values of the dictionary as a list
        return list(clients_dict.values())
        
    except Exception as e:
        print(f"Error fetching clients: {e}")
        raise HTTPException(status_code=500, detail="Failed to load clients.")

@app.delete("/admin/clients/{client_id}")
async def delete_client(client_id: str):
    db = get_supabase_admin_client()
    try:
        db.table('clients').delete().eq('id', client_id).execute()
        return {"message": "Client deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/clients/{client_id}/assign")
async def assign_module_to_client(client_id: str, req: AssignModuleRequest):
    db = get_supabase_admin_client()
    try:
        # Insert into junction table
        db.table('client_modules').insert({
            "client_id": client_id, 
            "module_id": str(req.module_id)
        }).execute()
        return {"message": "Module assigned to client"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/admin/clients/{client_id}/unassign")
async def unassign_module_from_client(client_id: str, req: AssignModuleRequest):
    db = get_supabase_admin_client()
    try:
        # Delete the relationship from the junction table
        db.table('client_modules').delete().eq('client_id', client_id).eq('module_id', str(req.module_id)).execute()
        return {"message": "Module unassigned successfully"}
    except Exception as e:
        print(f"Error unassigning: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Assessment Endpoint (Updated) ---

@app.post("/admin/assessments", response_model=AssessmentResponse, status_code=201)
async def create_assessment(request: AssessmentCreateRequest):
    """
    Updated: No longer accepts module_id.
    """
    # 1. Create the Assessment Record (No module_id)
    assessment_id = create_assessment_record(
        [t.dict() for t in request.topics], 
        sum(t.count for t in request.topics),
        module_id=None # Explicitly None
    )

    # 2. Generate Questions (Same as before)
    all_generated_questions = []
    try:
        for topic_config in request.topics:
            generated_questions = generate_questions(
                topic=topic_config.topic_name, 
                total=topic_config.count, 
                distribution=topic_config.difficulty.dict()
            )
            if len(generated_questions) > topic_config.count:
                generated_questions = generated_questions[:topic_config.count]
            for q in generated_questions:
                q['topic'] = topic_config.topic_name
            all_generated_questions.extend(generated_questions)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unexpected error during generation.")

    # 3. Save to Database
    save_questions_to_db(assessment_id, all_generated_questions)

    return {
        "id": assessment_id,
        "topics": [t.dict() for t in request.topics],
        "total_questions": len(all_generated_questions),
        "message": f"Successfully generated {len(all_generated_questions)} questions."
    }

@app.post("/admin/assessments/config", response_model=AssessmentResponse, status_code=201)
async def create_assessment_config(request: AssessmentCreateRequest):
    """
    Creates an Assessment record with the topic configuration only.
    No questions are generated or saved yet. This is used for planning.
    """
    # 1. Create the Assessment Record (storing the config)
    # We sum up the counts to store as 'total_questions' for the record, 
    # even though the actual questions table is empty.
    assessment_id = create_assessment_record(
        [t.dict() for t in request.topics], 
        sum(t.count for t in request.topics),
        module_id=None,
        type = "AI"
    )

    # 2. Return the ID immediately (Skip AI Generation)
    return {
        "id": assessment_id,
        "topics": [t.dict() for t in request.topics],
        "total_questions": sum(t.count for t in request.topics),
        "message": f"Configuration saved successfully. You can now assign this to a module."
    }

@app.get("/admin/assessments")
async def get_all_assessments():
    """
    Fetch all assessments to display in the list.
    """
    db = get_supabase_admin_client()
    # Join with modules to see which module it belongs to, if any
    response = db.table('assessments').select("*, modules(name)").order("created_at", desc=True).execute()
    return response.data

@app.get("/admin/assessments/{assessment_id}/results")
async def get_assessment_results(assessment_id: str):
    """
    Fetches all submissions for an assessment, joined with student details.
    Ordered by score descending.
    """
    client = get_supabase_admin_client()
    try:
        # Select submissions and join with students table
        # 'students(*)' returns all columns from the related student row
        response = client.table('submissions').select("*, students(full_name, email)").eq('assessment_id', assessment_id).order('score', desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
@app.post("/admin/assessments/manual", status_code=201)
async def create_manual_assessment(req: ManualAssessmentRequest):
    """
    Endpoint to manually create an assessment with pre-written questions.
    """
    client = get_supabase_admin_client()
    
    # 1. Create Assessment Record
    assessment_data = {
        "topic": [{"name": req.topic, "count": len(req.questions)}], # Summary format
        "total_questions": len(req.questions),
        "difficulty_distribution": {"type": "manual"}, # Placeholder
        "module_id": str(req.module_id) if req.module_id else None,
        "type": "Manual"
    }
    
    try:
        resp = client.table('assessments').insert(assessment_data).execute()
        assessment_id = resp.data[0]['id']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Error: {e}")

    # 2. Manually Save Questions
    questions_to_insert = []
    for q in req.questions:
        questions_to_insert.append({
            "assessment_id": str(assessment_id),
            "topic": req.topic, # Tag with the main topic
            "question_text": q.question_text,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "difficulty": q.difficulty
        })
    
    try:
        client.table('questions').insert(questions_to_insert).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save manual questions.")

    return {
        "id": assessment_id,
        "message": f"Successfully created assessment with {len(req.questions)} manual questions."
    }

@app.post("/admin/modules/{module_id}/add-assessment")
async def add_assessment_to_module(module_id: str, req: AssignAssessmentRequest):
    """
    Links an existing assessment to a module.
    """
    db = get_supabase_admin_client()
    try:
        # Update the assessment to point to this module
        db.table('assessments').update({"module_id": module_id}).eq('id', str(req.assessment_id)).execute()
        return {"message": "Assessment added to module"}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/assessments/{assessment_id}/remove-assessment")
async def remove_assessment_from_module(assessment_id: str):
    """
    Removes a module link from an assessment (sets module_id to null).
    """
    db = get_supabase_admin_client()
    try:
        db.table('assessments').update({"module_id": None}).eq('id', assessment_id).execute()
        return {"message": "Assessment removed from module"}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/signup", status_code=201)
async def signup(req: SignupRequest):
    """
    1. Creates Supabase Auth User.
    2. Inserts into public.profiles with the selected role.
    """
    admin_client = get_supabase_admin_client()
    
    # 1. Create Auth User
    try:
        user_res = admin_client.auth.admin.create_user({
            "email": req.email,
            "password": req.password,
            "email_confirm": True
        })
        user_id = str(user_res.user.id)
        print(f"DEBUG: Created User ID: {user_id}")
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create auth user: {e}")

    # 2. Create Profile Entry
    try:
        profile_data = {
            "id": user_id,
            "role": req.role
        }
        print(f"DEBUG: Inserting Profile: {profile_data}")
        admin_client.table('profiles').insert(profile_data).execute()
    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user profile.")

    return {"message": "User created successfully", "user_id": user_id}

@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        # Use the standard client for login
        client = get_supabase_client() 
        response = client.auth.sign_in_with_password({
            "email": form_data.username,
            "password": form_data.password
        })
        return {"access_token": response.session.access_token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

@app.get("/users/me")
async def read_users_me(current_user = Depends(get_current_user)):
    return current_user

@app.post("/admin/students", status_code=201)
async def create_student(student: StudentCreate):
    admin = get_supabase_admin_client()
    
    data = {
        "email": student.email,
        "password": student.password, 
        "full_name": student.full_name,
        "client_id": str(student.client_id), 
        "role": student.role,
        "phone": student.phone  # <--- ADD THIS LINE
    }
    
    try:
        response = admin.table('students').insert(data).execute()
        return response.data[0]
    except Exception as e:
        # ... existing error handling ...
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/students")
async def get_students():
    """
    Fetches all students to display in the Admin Dashboard.
    """
    admin = get_supabase_admin_client()
    try:
        # Select all columns
        response = admin.table('students').select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching students: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/student/login", response_model=Token)
async def student_login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Custom login for students stored in the 'students' table.
    """
    admin = get_supabase_admin_client()
    
    try:
        # 1. Check if email exists in students table
        response = admin.table('students').select("*").eq('email', form_data.username).execute()
        
        if not response.data:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
            
        student_record = response.data[0]
        
        # 2. Verify Password (WARNING: Comparing plain text passwords here)
        # In production, use passlib.context to check hashed passwords
        if student_record['password'] != form_data.password:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
            
        # 3. Generate Token
        access_token = create_student_token(student_record['email'], str(student_record['id']))
        
        return {"access_token": access_token, "token_type": "bearer"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Student Login Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
@app.get("/student/dashboard")
async def get_student_dashboard(current_user = Depends(get_current_user)):
    """
    Returns Client info and all Modules/Assessments assigned to the student's client.
    """
    # 1. Authorization Check
    if current_user.get('role') != 'student':
        raise HTTPException(status_code=403, detail="Access denied. Students only.")

    admin = get_supabase_admin_client()
    
    try:
        # 2. Get Student's Client ID
        student_resp = admin.table('students').select("client_id").eq('id', current_user['id']).single().execute()
        if not student_resp.data:
            raise HTTPException(status_code=404, detail="Student profile not found")
        
        client_id = student_resp.data.get('client_id')
        
        if not client_id:
            # Student exists but has no client assigned
            return {"client": None, "modules": []}

        # 3. Get Client Details
        client_resp = admin.table('clients').select("*").eq('id', client_id).single().execute()
        client_data = client_resp.data

        # 4. Get Modules assigned to this Client (via client_modules junction table)
        # We fetch the 'modules' nested inside the 'client_modules' table
        cm_resp = admin.table('client_modules').select("modules(*)").eq('client_id', client_id).execute()
        
        modules_list = []
        for item in cm_resp.data:
            if item.get('modules'):
                modules_list.append(item['modules'])

        # 5. Enrich Modules with their Assessments
        enriched_modules = []
        for mod in modules_list:
            mod_id = mod['id']
            
            # Fetch assessments linked to this specific module
            ass_resp = admin.table('assessments').select("*").eq('module_id', mod_id).execute()
            
            enriched_modules.append({
                "id": mod['id'],
                "name": mod['name'],
                "description": mod.get('description', ''),
                "assessments": ass_resp.data
            })

        return {
            "client": client_data,
            "modules": enriched_modules
        }

    except Exception as e:
        print(f"Error loading student dashboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard data")
    
@app.get("/student/assessments/{assessment_id}/questions")
async def get_assessment_questions(assessment_id: str, current_user = Depends(get_current_user)):
    """Fetches questions for Manual assessments."""
    if current_user.get('role') != 'student':
        raise HTTPException(status_code=403, detail="Students only.")
    
    admin = get_supabase_admin_client()
    
    # 1. Check if assessment is Manual
    ass_resp = admin.table('assessments').select("type").eq('id', assessment_id).single().execute()
    if not ass_resp.data or ass_resp.data.get('type') != 'Manual':
        raise HTTPException(status_code=400, detail="Assessment is not Manual or not found.")
        
    # 2. Fetch questions
    q_resp = admin.table('questions').select("*").eq('assessment_id', assessment_id).execute()
    return q_resp.data

@app.get("/student/assessments/{assessment_id}/generate")
async def generate_assessment_questions(assessment_id: str, current_user = Depends(get_current_user)):
    """Generates questions for AI assessments on the fly (not saved to DB)."""
    if current_user.get('role') != 'student':
        raise HTTPException(status_code=403, detail="Students only.")
    
    admin = get_supabase_admin_client()
    
    # 1. Get Assessment Config
    ass_resp = admin.table('assessments').select("topic").eq('id', assessment_id).single().execute()
    if not ass_resp.data:
        raise HTTPException(status_code=404, detail="Assessment not found")
    
    config_list = ass_resp.data.get('topic') 
    if not config_list:
        raise HTTPException(status_code=400, detail="Assessment configuration is missing.")

    # 2. Generate Questions
    all_generated_questions = []
    try:
        from models import generate_questions 
        
        for topic_config in config_list:
            generated = generate_questions(
                topic=topic_config.get('topic_name') or topic_config.get('topic'), 
                total=topic_config.get('count'), 
                distribution=topic_config.get('difficulty', {})
            )
            
            if len(generated) > topic_config.get('count'):
                generated = generated[:topic_config.get('count')]
            
            # --- MAPPING LOGIC (NEW) ---
            # Ensure correct_answer is a letter (A, B, C, D)
            for q in generated:
                options = q.get('options', [])
                ca = q.get('correct_answer')
                
                # If AI returned text instead of letter, map it
                if isinstance(ca, str) and ca not in ['A', 'B', 'C', 'D']:
                    if ca in options:
                        # Find index and convert to Letter (0->A, 1->B...)
                        idx = options.index(ca)
                        q['correct_answer'] = chr(65 + idx)
                # -------------------------

                q['topic_display'] = topic_config.get('topic_name') or topic_config.get('topic')
            
            all_generated_questions.extend(generated)
            
    except Exception as e:
        print(f"AI Gen Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate questions.")

    return all_generated_questions


class SubmissionCreate(BaseModel):
    assessment_id: uuid.UUID
    score: float

@app.post("/student/submissions")
async def submit_submission(sub: SubmissionCreate, current_user = Depends(get_current_user)):
    """Saves the student's score."""
    if current_user.get('role') != 'student':
        raise HTTPException(status_code=403, detail="Students only.")
    
    admin = get_supabase_admin_client()
    
    data = {
        "student_id": current_user['id'],
        "assessment_id": str(sub.assessment_id),
        "score": sub.score
    }
    
    try:
        admin.table('submissions').insert(data).execute()
        return {"message": "Score saved successfully"}
    except Exception as e:
        print(f"Submission Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save score.")
