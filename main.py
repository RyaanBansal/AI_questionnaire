from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
import uuid
import os
from dotenv import load_dotenv
import uvicorn

# Imports from your existing files
from models import generate_questions
from database import get_supabase_admin_client

load_dotenv()

app = FastAPI(title="Admin Assessment API", version="1.2.0")

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

class AssignModuleRequest(BaseModel):
    module_id: uuid.UUID

# UPDATED: Assessment Schema now accepts an optional Module ID
class AssessmentCreateRequest(BaseModel):
    topics: List[TopicConfig] = Field(..., min_items=1)
    module_id: Optional[uuid.UUID] = None # NEW FIELD

class AssessmentResponse(BaseModel):
    id: uuid.UUID
    topics: List[dict]
    total_questions: int
    message: str

class SubmissionRecord(BaseModel):
    id: uuid.UUID
    student_id: str
    score: float
    created_at: str

# --- Helper Functions ---

def create_assessment_record(topics_config: list, total: int, module_id: Optional[uuid.UUID] = None) -> uuid.UUID:
    client = get_supabase_admin_client()
    
    # FIX: Create a valid JSON object for difficulty_distribution
    # Since we now have multiple topics with specific difficulties, 
    # we save the list of topics here as well to act as the 'distribution' record.
    
    data = {
        "topic": topics_config, 
        "total_questions": total,
        "difficulty_distribution": topics_config, # Store the topic list here to prevent the NULL error
        "module_id": str(module_id) if module_id else None
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
    client = get_supabase_admin_client()
    response = client.table('modules').select("*").execute()
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
    response = db.table('clients').select("*").execute()
    return response.data

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


# --- Assessment Endpoint (Updated) ---

@app.post("/admin/assessments", response_model=AssessmentResponse, status_code=201)
async def create_assessment(request: AssessmentCreateRequest):
    
    # 1. Create the Assessment Record
    assessment_id = create_assessment_record(
        [t.dict() for t in request.topics], 
        sum(t.count for t in request.topics),
        request.module_id
    )

    # 2. Generate Questions for each topic
    all_generated_questions = []
    
    try:
        for topic_config in request.topics:
            print(f"Generating {topic_config.count} questions for {topic_config.topic_name}...")
            
            # Generate questions
            generated_questions = generate_questions(
                topic=topic_config.topic_name, 
                total=topic_config.count, 
                distribution=topic_config.difficulty.dict()
            )
            
            # FIX: Strictly slice the list to match the exact count requested
            if len(generated_questions) > topic_config.count:
                generated_questions = generated_questions[:topic_config.count]
                
            # Tag topic
            for q in generated_questions:
                q['topic'] = topic_config.topic_name
                
            all_generated_questions.extend(generated_questions)
            
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"AI Generation failed: {str(e)}")
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

@app.get("/admin/assessments/{assessment_id}/results", response_model=List[SubmissionRecord])
async def get_assessment_results(assessment_id: str):
    client = get_supabase_admin_client()
    try:
        uuid_id = uuid.UUID(assessment_id)
        response = client.table('submissions').select("*").eq('assessment_id', str(uuid_id)).execute()
        return response.data
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Assessment ID format.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
