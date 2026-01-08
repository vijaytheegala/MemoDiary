import os
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple
import json
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from app.storage import storage
from app.key_manager import key_manager

def safe_print(text: str):
    """Utility to print UTF-8 text safely on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

MEMORY_EXTRACTION_PROMPT = """
You are a Memory Extractor. Your goal is to identify and extract key facts and structured metadata from the user's input for a long-term memory database.

**CORE ODJECTIVE:**
From every input, intelligently extract and store meaningful keywords and entities such as people names, events, objects, emotions, dates, and contexts.

**EXTRACTION RULES:**
1. **Facts**: Extract explicit facts.
   - **People**: Names (e.g., "Kunal", "Mom").
   - **Events**: "Trip to Goa", "Birthday party", "Meeting".
   - **Objects**: "PS5", "Car", "Gift", "Wallet".
   - **Emotions**: "Happy", "Anxious", "Excited".
   - **Dates/Time**: "2025", "January", "Yesterday".
2. **Context**: Ignore filler words ("I think", "maybe"). Focus on the core information.

**METADATA FIELDS:**
You MUST classify the entry with these fields:
- **event_type**: Choose ONE: [birthday, interview, travel, health, work, relationship, education, purchase, general_observation].
- **topics**: A list of **NORMALIZED KEYWORDS/TAGS**. These should be single words or short phrases suitable for search indexing (e.g., "ps5", "kunal", "goa", "gift").
- **importance**: [normal, emotional, milestone].

**OUTPUT FORMAT (JSON ONLY):**
{
  "event_type": "purchase",
  "topics": ["ps5", "gaming", "sony", "gift"],
  "importance": "normal",
  "facts": [
    {"type": "object", "content": "User bought a PS5"},
    {"type": "person", "content": "Kunal (friend)"},
    {"type": "date", "content": "2025-01-01"}
  ]
}

**EXAMPLES:**
Input: "I bought a PS5 for Kunal's birthday."
Output:
{
  "event_type": "purchase",
  "topics": ["ps5", "kunal", "birthday", "gift"],
  "importance": "normal",
  "facts": [
    {"type": "object", "content": "User bought a PS5"},
    {"type": "person", "content": "Kunal"},
    {"type": "event", "content": "Kunal's Birthday"}
  ]
}
"""

class MemoryProcessor:
    def __init__(self):
        pass

    def _get_client(self):
        key = key_manager.get_next_key()
        if key:
            # UPGRADE: Standardization on 2.0 Flash (v1alpha) for consistent behavior
            return genai.Client(api_key=key, http_options={'api_version': 'v1alpha'})
        return None

    async def process_entry(self, session_id: str, text: str, entry_id: int):
        """
        Background task to extract facts and save them to the database.
        """
        client = self._get_client()
        if not client or not entry_id:
            return

        try:
            safe_print(f"DEBUG: Processing memory for: {text[:30]}...")
            
            # UPGRADE: 2.0 Flash for accurate extraction
            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=MEMORY_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            text_res = response.text.strip()
            data = json.loads(text_res)
            
            # Save Metadata
            e_type = data.get("event_type", "general_observation")
            topics = data.get("topics", [])
            importance = data.get("importance", "normal")
            
            storage.update_entry_metadata(entry_id, event_type=e_type, topics=topics, importance=importance)
            
            # Save Facts
            facts = data.get("facts", [])
            
            if facts:
                safe_print(f"🧠 EXTRACTED MEMORIES ({e_type}, {importance}): {facts}")
                for fact in facts:
                    # fact is now a dict: {"type": "...", "content": "..."}
                    f_type = fact.get("type", "detail")
                    f_content = fact.get("content", "")
                    if f_content:
                        storage.save_fact(entry_id, f_type, f_content)
            
        except Exception as e:
            safe_print(f"Error processing memory via Gemini: {e}")

# Global instance
memory_processor = MemoryProcessor()
