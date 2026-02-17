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
You are a Memory Extractor. Your goal is to extract structured, atomic facts from the user's diary entry for a long-term memory index.

**CORE OBSESSION**:
Extract PERMANENT, RETRIEVABLE facts about the user's life, preferences, and key entities.
Do NOT summarize the text. Extract specific "key-value" pairs.

**TARGET MEMORY TYPES**:
1. **profile**: Name, age, gender.
2. **pet**: Pet names, breeds, traits.
3. **event**: Life events (birthdays, anniversaries, trips).
4. **preference**: Likes/dislikes (food, color, music, movies).
5. **work**: Job title, company, projects, colleagues.
6. **education**: School, degree, major.
7. **health**: Allergies, conditions, medications.
8. **location**: Current city, hometown, addresses.
9. **relationship**: Family members, friends, partners.

**NEW: TOPIC STATE UPDATES**:
Also identify if the user's "Current State" for a specific life dimension has changed or was mentioned.
Topics: `health`, `food`, `routine`, `work`, `travel_preferences`.
Example: "I have a cold" -> topic: "health", state: "Has a cold (Jan 10)".
Example: "I am going vegan" -> topic: "food", state: "Vegan diet".

**OUTPUT FORMAT (JSON ONLY)**:
Return a JSON object with:
1. `memories`: List of atomic facts (as defined above).
2. `topic_updates`: List of state objects: `{"topic": "...", "state": "..."}`.

**EXAMPLES**:

Input: "My dog's name is Bhima. I usually wake up at 6am to walk him."
Output:
{
  "memories": [
    {"memory_type": "pet", "memory_key": "dog_name", "memory_value": "Bhima", "confidence": 1.0}
  ],
  "topic_updates": [
    {"topic": "routine", "state": "Wakes up at 6am for dog walk"}
  ]
}

If no relevant permanent facts or updates are found, return empty lists.
"""

DAILY_SUMMARY_PROMPT = """
You are a Daily Diarist. Your goal is to summarize the user's day based on their entries.

TASK:
1. Create a concise summary of the day's events (max 3 sentences).
2. Identify key concrete events (list strings).
3. Determine the dominant mood (one emoji).
4. **ESTIMATE METRICS (1-10)**:
   - `energy`: 1 (Exhausted) to 10 (Hyper). Default 5.
   - `stress`: 1 (Zen) to 10 (Panic). Default 3.
   - `sleep`: Estimated hours (e.g., 7) or Quality (1-10) if mentioned. If unknown, return -1.

OUTPUT JSON:
{
  "summary": "...",
  "key_events": ["..."],
  "dominant_mood": "Mood",
  "metrics": {
      "energy": 5,
      "stress": 3,
      "sleep": -1
  }
}
"""

from app.utils.ai_utils import generate_with_retry

class MemoryProcessor:
    def __init__(self):
        pass

    async def process_entry(self, session_id: str, text: str, entry_id: int):
        """
        Background task to extract facts and save them to the database.
        Includes retry logic via shared utility.
        """
        if not entry_id: return

        try:
            # safe_print(f"DEBUG: Processing memory for: {text[:30]}...")
            
            # 1. Fact Extraction
            response = await generate_with_retry(
                model_name="gemini-2.0-flash", 
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=MEMORY_EXTRACTION_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            
            text_res = response.text.strip()
            data = json.loads(text_res)
            
            memories = data.get("memories", [])
            topics = data.get("topic_updates", [])
            
            if memories:
                safe_print(f"🧠 STRUCTURING MEMORY: Found {len(memories)} items.")
                for mem in memories:
                    m_type = mem.get("memory_type")
                    m_key = mem.get("memory_key")
                    m_val = mem.get("memory_value")
                    conf = mem.get("confidence", 0.5)
                    
                    if m_type and m_key and m_val:
                            storage.add_memory_item(session_id, m_type, m_key, m_val, entry_id, conf)

            if topics:
                safe_print(f"🔄 TOPIC UPDATES: Found {len(topics)} items.")
                for t in topics:
                    topic = t.get("topic")
                    state = t.get("state")
                    if topic and state:
                        # We append date to state to give it context
                        date_str = datetime.now().strftime("%Y-%m-%d")
                        full_state = f"{state} ({date_str})"
                        storage.upsert_topic_state(session_id, topic, full_state)
            
            # 2. Lazy Daily Summary Update
            if len(text) > 20: 
                    await self.update_daily_summary(session_id)

        except Exception as e:
            safe_print(f"Error processing memory via Gemini: {e}")

    async def update_daily_summary(self, session_id: str):
        """Updates the daily summary for the current day with retry logic via shared utility."""
        today_date = datetime.now().strftime("%Y-%m-%d")
        start = f"{today_date}T00:00:00"
        end = f"{today_date}T23:59:59"
        
        entries = storage.get_entries_in_range(session_id, start, end)
        if not entries: return

        # Combine text
        combined_text = "\n".join([f"- {e['text']}" for e in entries])
        
        try:
            response = await generate_with_retry(
                model_name="gemini-2.0-flash", 
                contents=combined_text,
                config=types.GenerateContentConfig(
                    system_instruction=DAILY_SUMMARY_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )
            data = json.loads(response.text.strip())
            
            summary = data.get("summary", "")
            key_events = json.dumps(data.get("key_events", []))
            mood = data.get("dominant_mood", "😐")
            
            storage.upsert_daily_summary(session_id, today_date, summary, key_events, mood)
            
            # SAVE METRICS (New)
            metrics = data.get("metrics", {})
            if metrics:
                energy = metrics.get("energy", 5)
                stress = metrics.get("stress", 3)
                sleep = metrics.get("sleep", -1)
                
                if energy is None: energy = 5
                if stress is None: stress = 3
                if sleep is None: sleep = -1
                
                storage.upsert_daily_metrics(session_id, today_date, energy, stress, sleep)
            
            safe_print(f"📅 UPDATED DAILY SUMMARY + METRICS for {today_date}")

        except Exception as e:
            safe_print(f"Error updating daily summary: {e}")

# Global instance
memory_processor = MemoryProcessor()
