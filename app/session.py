from typing import Dict, List, Optional
import time

from app.storage import storage

# Simple in-memory storage: {session_id: [messages]}
# Message format: {"role": "user"|"assistant", "content": "..."}
sessions: Dict[str, List[Dict[str, str]]] = {}

MAX_HISTORY_LENGTH = 20  # Keep last 20 messages to avoid token limits

def get_session_history(session_id: str) -> List[Dict[str, str]]:
    """Retrieve conversation history for a session."""
    # Ideally should fetch from DB on restart, but sticking to simple cache for now
    # If cache miss, maybe hydrate from storage?
    if session_id not in sessions:
        # Hydrate from DB (MVP: Last 20 messages)
        recent_entries = storage.get_recent_entries(session_id, limit=20)
        # Convert to session format (reverse order as get_recent returns DESC)
        history = []
        for e in reversed(recent_entries):
             history.append({"role": "user" if e['role'] == 'user' else 'assistant', "content": e['text']})
        sessions[session_id] = history
        
    return sessions.get(session_id, [])

def add_message_to_session(session_id: str, role: str, content: str) -> int:
    """Add a message to the session history and Persist to DB."""
    if session_id not in sessions:
        # Trigger hydration
        get_session_history(session_id)
    
    sessions[session_id].append({"role": role, "content": content})
    
    # Trim history if it gets too long
    if len(sessions[session_id]) > MAX_HISTORY_LENGTH:
        sessions[session_id] = sessions[session_id][-MAX_HISTORY_LENGTH:]

    # PERSIST TO DB
    # Map role: 'assistant' -> 'model' for DB
    db_role = "model" if role == "assistant" else role
    entry_id = storage.add_entry(session_id, db_role, content)
    return entry_id

def clear_session(session_id: str):
    """Clear a session's history."""
    if session_id in sessions:
        del sessions[session_id]
