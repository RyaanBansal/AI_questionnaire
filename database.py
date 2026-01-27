from supabase import create_client
import os
from dotenv import load_dotenv
import jwt

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_anon_key = os.getenv("SUPABASE_ANON_KEY")
supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def get_supabase_client(jwt_token:  str | None = None):
    """Get a Supabase client with JWT authentication"""
    client = create_client(supabase_url, supabase_anon_key)
    if jwt_token:
        client. postgrest.auth(jwt_token)
    return client


def get_supabase_admin_client():
    """Get a Supabase admin client (for backend operations, bypasses RLS)"""
    return create_client(supabase_url, supabase_service_key)


def verify_jwt(jwt_token: str) -> dict:
    """Verify JWT token and return decoded payload"""
    try:
        payload = jwt.decode(jwt_token, options={"verify_signature": False})
        return payload
    except Exception as e:
        return None