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
from app.middleware.rate_limiter import chat_limiter # Restored import
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

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.png")

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy"}

from typing import Optional

# --- Models ---
class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None) 
    message: str = Field(..., min_length=1, max_length=2000)
    stream: bool = True # Default to True for new experience

class ChatResponse(BaseModel):
    response: str
    mood: str
    new_session_id: Optional[str] = None

# --- Helpers ---
def generate_secure_id():
    """Generates a secure, random user ID."""
    return f"u_{secrets.token_urlsafe(16)}"


@app.post("/api/chat")
async def chat(request: Request, chat_req: ChatRequest):
    session_id = chat_req.session_id
    user_message = chat_req.message

    # Rate limiting
    limit_key = session_id if (session_id and session_id != "null") else request.client.host
    if not chat_limiter.is_allowed(limit_key):
        raise HTTPException(status_code=429, detail="TOO_MANY_REQUESTS")

    try:
        new_id_generated = None
        
        # 0. Generate SECURE ID if missing
        if not session_id or session_id == "null" or len(session_id) < 5:
            session_id = generate_secure_id()
            new_id_generated = session_id
            logger.info(f"Generated new secure session ID: {session_id}")
            from app.storage import storage
            storage.create_user(session_id)

        # 1. Retrieve history
        history = get_session_history(session_id)

        # 2. Add User Msg to History (In-Memory)
        add_message_to_session(session_id, "user", user_message)

        # 3. Stream or Block
        if chat_req.stream:
            async def event_generator():
                # Send Session ID first if new
                if new_id_generated:
                    yield f"event: session_id\ndata: {new_id_generated}\n\n"
                
                # Get the stream generator from AI
                ai_stream = await get_ai_response(session_id, history, user_message, stream=True)
                
                full_response = ""
                async for chunk in ai_stream:
                    if chunk:
                        full_response += chunk
                        # Escape newlines for SSE data payload logic if needed, 
                        # but standard event stream handles it if we are careful.
                        # Using JSON data payload is safer.
                        yield f"data: {chunk}\n\n"
                
                # Update Session History with full response
                if full_response:
                    add_message_to_session(session_id, "assistant", full_response)
                
                # Send 'done' event? or close.
                yield "event: done\ndata: [DONE]\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        else:
             # Standard JSON fallback
            ai_text, mood = await get_ai_response(session_id, history, user_message, stream=False)
            add_message_to_session(session_id, "assistant", ai_text)
            return ChatResponse(response=ai_text, mood=mood, new_session_id=new_id_generated)

    except HTTPException as he:
        logger.warning(f"HTTP {he.status_code}: {he.detail}")
        raise he
    except Exception as e:
        logger.error(f"FATAL ERR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"ERR_INTERNAL: {str(e)}")


@app.api_route("/api/tts", methods=["GET", "POST"])
async def text_to_speech(request: Request):
    """
    Streaming TTS Endpoint. 
    Accepts 'text' and 'session_id' as query params (GET) or JSON body (POST).
    """
    try:
        # 1. Parse Input
        if request.method == "POST":
            data = await request.json()
            text = data.get("text")
            session_id = data.get("session_id")
        else:
            text = request.query_params.get("text")
            session_id = request.query_params.get("session_id")

        if not text:
            raise HTTPException(status_code=400, detail="Missing text")

        # 2. Generate Audio Stream
        # Use a generator to stream bytes
        async def audio_streamer():
            try:
                async for chunk in tts_engine.generate_speech_stream(text):
                    yield chunk
            except Exception as e:
                logger.error(f"TTS Stream Error: {e}")
                # If headers already sent, we can't do much but close stream
                return

        return StreamingResponse(
            audio_streamer(), 
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no" # Nginx
            }
        )

    except Exception as e:
        logger.error(f"TTS Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/startup")
async def startup_check(request: Request):
    """
    Initial handshake. Returns a welcome message.
    """
    try:
        data = await request.json()
        session_id = data.get("session_id")
        
        # Logic similar to chat but simpler
        if not session_id or session_id == "null":
            session_id = generate_secure_id()
            from app.storage import storage
            storage.create_user(session_id)
            
            # Welcome new user
            return {
                "session_id": session_id,
                "message": "Hello there. I'm Memo. What can I call you?",
                "mood": "👋"
            }
        else:
             # Returning user check?
             # For now just ack
             return {
                 "session_id": session_id,
                "message": "Welcome back.",
                "mood": "👋"
             }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
