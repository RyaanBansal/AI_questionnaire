from google import genai 
import os
import json
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def generate_questions(topic: str, total: int, distribution: dict):
    """
    Calls the NEW Gemini SDK to generate MCQs.
    """
    model_name = "gemini-2.5-flash-lite"

    prompt = f"""
    Generate {total} multiple-choice questions about '{topic}'.
    Difficulty distribution: {distribution}.

    Return ONLY a JSON array of objects with this exact structure:
    [
        {{
            "question_text": "The question text here?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "Whichever answer is correct",
            "difficulty": "Set according to the distribution between Easy, Medium, Hard"
        }}
    ]
    Do not include markdown formatting (no ```json). Just raw JSON.
    """

    try:
        # 3. Call the API using the client (New Syntax)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            
        )

        # 4. Extract the text from the response
        content = response.text.strip()
        
        # Clean up markdown if the AI adds it back anyway
        if content.startswith("```"):
            content = content.strip("`").replace("json", "")

        questions = json.loads(content)
        return questions
        
    except Exception as e:
        print(f"AI Error: {e}")
        # Print the raw response for debugging if JSON parsing fails
        if 'response' in locals():
            print(f"Raw AI Response: {response.text}")
        raise ValueError("Failed to generate valid questions from AI.")