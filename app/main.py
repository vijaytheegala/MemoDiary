from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uuid
import os
import secrets
import string
import logging
import traceback
import io

from app.session import get_session_history, add_message_to_session
from app.ai import get_ai_response
from app.utils.tts_engine import tts_engine
from app.transcriber import transcriber
from app.middleware.rate_limiter import chat_limiter # Restored import
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field


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
print("--- SERVER RELOADED: ADMIN PIN LOGIC ACTIVE ---") # Force Reload Trigger

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


from starlette.background import BackgroundTask
from app.memory import memory_processor

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

        # 2. Add User Msg to History (In-Memory + DB)
        # REMOVED: Delegate to app/ai.py to avoid duplication
        # user_entry_id = add_message_to_session(session_id, "user", user_message)

        # Prepare Background Task for Learning
        # REMOVED: Delegate to app/ai.py
        # learning_task = BackgroundTask(...)

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
                # REMOVED: Delegate to app/ai.py
                # if full_response:
                #    add_message_to_session(session_id, "assistant", full_response)
                
                # Send 'done' event? or close.
                yield "event: done\ndata: [DONE]\n\n"

            return StreamingResponse(
                event_generator(), 
                media_type="text/event-stream"
                # background=learning_task # REMOVED
            )

        else:
             # Standard JSON fallback
            ai_text, mood = await get_ai_response(session_id, history, user_message, stream=False)
            
            # REMOVED: Delegate to app/ai.py
            # add_message_to_session(session_id, "assistant", ai_text)
            # asyncio.create_task(memory_processor.process_entry(session_id, user_message, user_entry_id))
            
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

@app.post("/api/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    """
    Transcribe uploaded audio file.
    """
    try:
        # Read file
        audio_bytes = await file.read()
        mime_type = file.content_type or "audio/webm"
        
        # Transcribe
        text = await transcriber.transcribe_audio(audio_bytes, mime_type)
        
        return {"text": text}
    except Exception as e:
        logger.error(f"Transcribe API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- ADMIN PANEL ---

# Secure constants (PIN: 148314)
ADMIN_SALT_HEX = "7d808147a534abdcd708343e801868e7"
ADMIN_PIN_HASH_HEX = "8d2c5f5d5458e6c44d208a4df2665419b483bacbd4312815c99c4b26aca624cf"

# In-memory admin session store
ACTIVE_ADMIN_TOKENS = set()

class AdminLoginRequest(BaseModel):
    pin: str

@app.post("/api/admin/login")
async def admin_login(creds: AdminLoginRequest):
    import hashlib
    import secrets

    print(f"DEBUG: Login attempt with PIN") 

    # Verify PIN using Hash
    try:
        salt = bytes.fromhex(ADMIN_SALT_HEX)
        target_hash = bytes.fromhex(ADMIN_PIN_HASH_HEX)
        
        # Compute hash of input
        computed_key = hashlib.pbkdf2_hmac('sha256', creds.pin.encode('utf-8'), salt, 100000)
        
        # Constant time comparison to prevent timing attacks
        if not secrets.compare_digest(computed_key, target_hash):
            print("DEBUG: PIN hash mismatch")
            raise HTTPException(status_code=401, detail="Invalid PIN")
            
    except Exception as e:
        logger.error(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Success -> Generate Token
    token = secrets.token_urlsafe(32)
    ACTIVE_ADMIN_TOKENS.add(token)
    
    return {"token": token}

@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    from app.storage import storage
    
    # 1. Check Auth Header: "Authorization: Bearer <token>"
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split(" ")[1]
    
    if token not in ACTIVE_ADMIN_TOKENS:
        raise HTTPException(status_code=403, detail="Unauthorized access")
    
    # 2. Fetch Data
    stats = storage.get_analytics_stats()
    return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
