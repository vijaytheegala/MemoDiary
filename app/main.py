from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uuid
import os
import secrets
import string
import logging
import traceback

from app.session import get_session_history, add_message_to_session
from app.ai import get_ai_response
from app.utils.tts_engine import tts_engine
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import io

from logging.handlers import RotatingFileHandler

# Configure logging with rotation for production readiness
if not os.path.exists('logs'):
    os.makedirs('logs', exist_ok=True)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = 'logs/server.log'

# 5MB per file, keep 3 backup files
rotating_handler = RotatingFileHandler(
    log_file, maxBytes=5*1024*1024, backupCount=3
)
rotating_handler.setFormatter(log_formatter)
rotating_handler.setLevel(logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(rotating_handler)
# Also log to console for development visibility
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

app = FastAPI(title="MemoDiary")

# CORS (Safe defaults for deployment - adjust allowed_origins as needed)
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Add production domains here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"], # Restricted from ["*"]
    allow_headers=["*"],
)

# Serve static files (Frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}

from typing import Optional

class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None) 
    message: str = Field(..., min_length=1, max_length=2000)

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    session_id: Optional[str] = Field(None)

class ChatResponse(BaseModel):
    response: str
    mood: str
    new_session_id: Optional[str] = None

class AuthResponse(BaseModel):
    session_id: str
    status: str

def generate_secure_id():
    return secrets.token_urlsafe(12)

from app.middleware.rate_limiter import chat_limiter, auth_limiter, tts_limiter

@app.post("/api/auth/anonymous", response_model=AuthResponse)
async def anonymous_auth(request: Request):
    """
    Generates a unique, secure anonymous user ID and initializes a session.
    """
    client_ip = request.client.host
    if not auth_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="TOO_MANY_REQUESTS")

    try:
        # Generate a secure ID
        session_id = generate_secure_id()
        # Initialize in storage
        from app.storage import storage
        storage.create_user(session_id)
        
        logger.info(f"Created new anonymous user: {session_id}")
        return AuthResponse(session_id=session_id, status="ready")
    except Exception as e:
        logger.error(f"Auth Error: {e}")
        raise HTTPException(status_code=500, detail="AUTH_ERROR")

class StartupRequest(BaseModel):
    session_id: Optional[str] = Field(None)

@app.post("/api/startup")
async def startup(request: Request, startup_req: StartupRequest):
    """
    Handles app startup/refresh.
    Returns: session_id (existing or new) + Welcome Message.
    """
    session_id = startup_req.session_id
    
    # Rate limit check (using IP if no session yet)
    limit_key = session_id if (session_id and session_id != "null") else request.client.host
    if not auth_limiter.is_allowed(limit_key):
        raise HTTPException(status_code=429, detail="TOO_MANY_REQUESTS")

    # 1. Validate / Generate Session ID
    if not session_id or session_id == "null" or len(session_id) < 5:
        session_id = generate_secure_id()
        # Initialize in storage logic handled by ai.get_welcome_message if needed, 
        # but let's ensure it exists here to be safe.
        from app.storage import storage
        storage.create_user(session_id)
        logger.info(f"Generated new session ID at startup: {session_id}")

    try:
        # 2. Get Welcome Message
        from app.ai import get_welcome_message
        msg, mood = await get_welcome_message(session_id)
        
        return {
            "session_id": session_id,
            "message": msg,
            "mood": mood
        }
    except Exception as e:
        logger.error(f"Startup Error: {e}")
        raise HTTPException(status_code=500, detail="STARTUP_ERROR")

@app.post("/api/tts") # Switched from GET for privacy
async def get_tts(request: Request, tts_req: TTSRequest):
    """
    Generates and returns an audio stream for the given text.
    """
    session_id = tts_req.session_id
    text = tts_req.text

    if not tts_limiter.is_allowed(session_id or request.client.host):
        raise HTTPException(status_code=429, detail="TOO_MANY_REQUESTS")

    try:
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        if len(text) > 1000:
            raise HTTPException(status_code=400, detail="Text too long")
        
        # Streaming response directly specific to edge_tts generator
        return StreamingResponse(
            tts_engine.generate_speech_stream(text), 
            media_type="audio/mpeg"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"TTS Error: {e}")
        # Sanitize error detail
        raise HTTPException(status_code=500, detail="TTS_ERROR")

@app.get("/")
async def read_root():
    """Serve the main chat interface."""
    return FileResponse(os.path.join("static", "index.html"))

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, chat_req: ChatRequest):
    session_id = chat_req.session_id
    user_message = chat_req.message

    # Rate limiting
    # Use client IP if session_id is missing or 'null' string
    limit_key = session_id if (session_id and session_id != "null") else request.client.host
    if not chat_limiter.is_allowed(limit_key):
        raise HTTPException(status_code=429, detail="TOO_MANY_REQUESTS")

    try:
        new_id_generated = None
        
        # 0. Generate SECURE ID if missing or invalid pattern
        # Treat string "null" from JS localStorage as invalid
        if not session_id or session_id == "null" or len(session_id) < 5:
            session_id = generate_secure_id()
            new_id_generated = session_id
            logger.info(f"Generated new secure session ID: {session_id}")
            # Initialize user in storage
            from app.storage import storage
            storage.create_user(session_id)

        # 1. Retrieve history (scoped to session)
        history = get_session_history(session_id)

        # 2. Get AI Response
        ai_text, mood = await get_ai_response(session_id, history, user_message)

        # 3. Update In-Memory Session History
        add_message_to_session(session_id, "user", user_message)
        add_message_to_session(session_id, "assistant", ai_text)
        
        return ChatResponse(response=ai_text, mood=mood, new_session_id=new_id_generated)

    except HTTPException as he:
        logger.warning(f"HTTP {he.status_code} for session {session_id}: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"FATAL ERR for session {session_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Provide more detail in dev/debug, but stick to generic for now unless verified
        raise HTTPException(status_code=500, detail=f"ERR_INTERNAL: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
