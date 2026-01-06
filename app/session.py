from typing import Dict, List, Optional
import time

# Simple in-memory storage: {session_id: [messages]}
# Message format: {"role": "user"|"assistant", "content": "..."}
sessions: Dict[str, List[Dict[str, str]]] = {}

MAX_HISTORY_LENGTH = 20  # Keep last 20 messages to avoid token limits

def get_session_history(session_id: str) -> List[Dict[str, str]]:
    """Retrieve conversation history for a session."""
    return sessions.get(session_id, [])

def add_message_to_session(session_id: str, role: str, content: str):
    """Add a message to the session history."""
    if session_id not in sessions:
        sessions[session_id] = []
    
    sessions[session_id].append({"role": role, "content": content})
    
    # Trim history if it gets too long
    if len(sessions[session_id]) > MAX_HISTORY_LENGTH:
        sessions[session_id] = sessions[session_id][-MAX_HISTORY_LENGTH:]

def clear_session(session_id: str):
    """Clear a session's history."""
    if session_id in sessions:
        del sessions[session_id]
