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

def safe_print(text: str):
    """Utility to print UTF-8 text safely on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

MEMORY_EXTRACTION_PROMPT = """
You are a Memory Extractor. Your goal is to identify and extract key facts about the user's life, preferences, relationships, and major events from their diary entries.

Rules:
1. Extract FACTS only. Do not summarize the mood unless it's a major event or strong emotion.
2. Focus on:
   - **People**: Names and their relationship to user (e.g., "Sarah (friend)").
   - **Events**: Specific occurrences, meetings, celebrations.
   - **Places**: Locations visited or mentioned.
   - **Emotions**: Strong, non-transient feelings attached to events (e.g., "Felt grief about dog").
   - **Objects**: Important items mentioned (e.g., "Bought a new car", "lost my keys").
   - **Dates/Times**: "Birthday", "Anniversary", specific dates mentioned.
   - **Preferences**: Likes/dislikes.
3. Ignore transient, small talk ("I am sad today" without context), but capture "I am sad because X".
4. If no permanent facts are found, return valid JSON with empty list.

Input Format: User diary entry text.
Output Format: JSON only.
{
  "facts": [
    {"type": "person", "content": "Sarah (friend)"},
    {"type": "event", "content": "Went to Starbucks"},
    {"type": "preference", "content": "Hates coffee"}
  ]
}

Example:
Input: "I went to Starbucks with Sarah today. She ordered a latte. I hate coffee though. Also, bought a nice pen."
Output: {
  "facts": [
    {"type": "event", "content": "User went to Starbucks with Sarah"},
    {"type": "person", "content": "Sarah"},
    {"type": "preference", "content": "User hates coffee"},
    {"type": "object", "content": "User bought a nice pen"}
  ]
}
"""

class MemoryProcessor:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            self.client = genai.Client(
                api_key=self.api_key,
                http_options={'api_version': 'v1alpha'}
            )

    async def process_entry(self, session_id: str, text: str, entry_id: int):
        """
        Background task to extract facts and save them to the database.
        """
        if not self.client or not entry_id:
            return

        try:
            safe_print(f"DEBUG: Processing memory for: {text[:30]}...")
            
            # Using Gemini for Extraction
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=MEMORY_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            
            text_res = response.text.strip()
            data = json.loads(text_res)
            facts = data.get("facts", [])
            
            if facts:
                safe_print(f"🧠 EXTRACTED MEMORIES: {facts}")
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
