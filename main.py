from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any
import uuid
import os
from dotenv import load_dotenv
import uvicorn

# Imports from your existing files
from models import generate_questions
from database import get_supabase_admin_client

load_dotenv()

app = FastAPI(title="Admin Assessment API", version="1.0.0")

# --- Pydantic Schemas ---

class DifficultyDistribution(BaseModel):
    # Add alias="easy", alias="medium", etc.
    Easy: int = Field(..., ge=0, le=100, alias="easy")
    Medium: int = Field(..., ge=0, le=100, alias="medium")
    Hard: int = Field(..., ge=0, le=100, alias="hard")

    @validator('*', always=True)
    def check_sum(cls, v, values):
        # This logic still works because Pydantic maps 'easy' -> 'Easy' internally
        if 'Easy' in values and 'Medium' in values and 'Hard' in values:
            total = values['Easy'] + values['Medium'] + values['Hard']
            if total != 100:
                raise ValueError(f"Difficulty distribution must sum to 100%. Current sum: {total}%")
        return v
    
    class Config:
        # This allows the model to accept the alias ('easy') OR the field name ('Easy')
        populate_by_name = True
        
class AssessmentCreateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    total_questions: int = Field(..., gt=0)
    difficulty: DifficultyDistribution

class AssessmentResponse(BaseModel):
    id: uuid.UUID
    topic: str
    total_questions: int
    message: str

class SubmissionRecord(BaseModel):
    id: uuid.UUID
    student_id: str
    score: float
    created_at: str

# --- Helper Functions ---

def create_assessment_record(topic: str, total: int, distribution: dict) -> uuid.UUID:
    """
    Inserts into 'assessments' table.
    Schema: id, topic, total_questions, difficulty_distribution
    """
    client = get_supabase_admin_client()
    
    data = {
        "topic": topic,
        "total_questions": total,
        "difficulty_distribution": distribution  # Stored as JSONB per your schema
    }
    
    try:
        response = client.table('assessments').insert(data).execute()
        # Extract the UUID from the response
        return uuid.UUID(response.data[0]['id'])
    except Exception as e:
        print(f"DB Error creating assessment: {e}")
        raise HTTPException(status_code=500, detail="Failed to create assessment record.")

def save_questions_to_db(assessment_id: uuid.UUID, questions: list[dict]):
    """
    Inserts into 'questions' table.
    Schema: id, assessment_id, question_text, options, correct_answer, difficulty
    """
    client = get_supabase_admin_client()
    
    questions_to_insert = []
    for q in questions:
        questions_to_insert.append({
            "assessment_id": str(assessment_id), # FK must be string/UUID
            "question_text": q['question_text'],
            "options": q['options'],              # JSONB
            "correct_answer": q['correct_answer'],
            "difficulty": q['difficulty']         # Text: 'Easy', 'Medium', 'ard'
        })
    
    try:
        client.table('questions').insert(questions_to_insert).execute()
    except Exception as e:
        print(f"DB Error saving questions: {e}")
        raise HTTPException(status_code=500, detail="Failed to save generated questions.")

# --- Admin Endpoints ---

@app.post("/admin/assessments", response_model=AssessmentResponse, status_code=201)
async def create_assessment(request: AssessmentCreateRequest):
    """
    US-001 & US-002: 
    1. Validates difficulty sums to 100%.
    2. Creates Assessment Record (Parent).
    3. Calls AI to generate questions.
    4. Saves Questions (Children).
    """
    
    # 1. Create the Assessment config
    assessment_id = create_assessment_record(
        request.topic, 
        request.total_questions, 
        request.difficulty.dict()
    )

    # 2. Generate Questions via AI
    try:
        generated_questions = generate_questions(
            topic=request.topic, 
            total=request.total_questions, 
            distribution=request.difficulty.dict()
        )
    except ValueError as e:
        # US-008: Handle AI failure
        raise HTTPException(status_code=500, detail=f"AI Generation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unexpected error during generation.")

    # 3. Save to Database
    try:
        save_questions_to_db(assessment_id, generated_questions)
    except HTTPException:
        raise # Re-raise the HTTP exception from the helper

    return {
        "id": assessment_id,
        "topic": request.topic,
        "total_questions": len(generated_questions),
        "message": f"Successfully generated {len(generated_questions)} questions."
    }

@app.get("/admin/assessments/{assessment_id}/results", response_model=List[SubmissionRecord])
async def get_assessment_results(assessment_id: str):
    """
    US-007: View all student data for a specific assessment.
    Fetches from 'submissions' table.
    """
    client = get_supabase_admin_client()
    
    try:
        # Validate UUID format
        uuid_id = uuid.UUID(assessment_id)
        
        # Fetch all submissions for this assessment
        response = client.table('submissions').select("*").eq('assessment_id', str(uuid_id)).execute()
        
        return response.data
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Assessment ID format.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)