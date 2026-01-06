import os
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple
from app.storage import storage
from dotenv import load_dotenv
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

def safe_print(text: str):
    """Utility to print UTF-8 text safely on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

QUERY_ANALYSIS_PROMPT = """
You are a MemoDiary Query Analyzer. Your job is to determine the user's intent:
1. "personal_recall": Asking about their OWN past experiences, feelings, people they know, or events they've recorded in their diary.
   - REQUIREMENT: Usually contains "I", "me", "my", "we", or refers to specific personal names/relations.
   - Example: "What did I do yesterday?", "How was my mood?", "What did I say about Sarah?"
2. "general_info": Asking about the world, public events, news, weather, MATH, or facts.
   - REQUIREMENT: Questions about places (London, Vizag), public figures, definitions, or math.
   - CRITICAL: Arithmetic/Math questions (e.g., "What is 2 + 2?", "Calculate 5*5") MUST be "general_info".
   - CRITICAL: "What happened in [Place]?" is "general_info" unless it specifies "What did I do in [Place]".
   - Example: "What happened in Vizag?", "Who won the game?", "What is 2 + 2?", "Weather in London?"
3. "chat": Normal conversation, sharing CURRENT feelings, hello/goodbye, or general advice.
   - Example: "I'm feeling sad today", "Tell me a story", "Hi MEMO".

Output format (JSON only):
{
  "intent": "personal_recall" | "general_info" | "chat",
  "search_queries": ["keyword1", "keyword2"],
  "date_range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" } | null,
  "language_code": "en" | "es" | "te" | "hi" | ... (ISO 639-1 code of the user's input language)
}

SCENARIO NOTE: Even for "general_info", provide search keywords in case the user mentioned these general topics in their personal diary.

Examples:
- "What did I do yesterday?" (Ref: 2024-01-02) -> {"intent": "personal_recall", "search_queries": ["events", "activity"], "date_range": {"start": "2024-01-01", "end": "2024-01-01"}}
- "What happened last week?" (Ref: 2024-01-10) -> {"intent": "personal_recall", "search_queries": [], "date_range": {"start": "2024-01-03", "end": "2024-01-09"}, "language_code": "en"}
- "What happened in Vizag yesterday?" (Ref: 2024-01-02) -> {"intent": "general_info", "search_queries": ["Vizag", "events elsewhere"], "date_range": {"start": "2024-01-01", "end": "2024-01-01"}, "language_code": "en"}
- "What is 2 + 2?" -> {"intent": "general_info", "search_queries": [], "date_range": null, "language_code": "en"}
- "I am feeling sad." -> {"intent": "chat", "search_queries": [], "date_range": null, "language_code": "en"}
"""

class QueryEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if api_key:
            self.client = genai.Client(
                api_key=api_key,
                http_options={'api_version': 'v1alpha'}
            )

    async def analyze_query(self, text: str, current_time: str) -> Dict[str, Any]:
        """
        Determine if query needs context retrieval.
        """
        full_prompt = f"Current Time Reference: {current_time}\nInput: {text}"
        
        if not self.client:
            return {"intent": "chat", "search_queries": []}

        try:
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=QUERY_ANALYSIS_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            
            text_res = response.text.strip()
            import json
            data = json.loads(text_res)
            return data
        except Exception as e:
            # Fallback to English if detection fails
            return {"intent": "chat", "search_queries": [], "date_range": None, "language_code": "en"}

    def retrieve_context(self, session_id: str, search_queries: List[str], date_range: Dict[str, str] = None, intent: str = "chat") -> str:
        """
        Fetch relevant entries from storage scoped to session.
        """
        all_results = []
        
        # 1. Search by date range if provided
        if date_range and date_range.get("start") and date_range.get("end"):
            # Ensure we search the full day for start and end
            start = f"{date_range['start']}T00:00:00"
            end = f"{date_range['end']}T23:59:59"
            results = storage.get_entries_in_range(session_id, start, end)
            all_results.extend(results)

        # 2. Search by keywords
        if search_queries:
            for q in search_queries:
                if q: # guard against empty strings
                    # Increase limit to ensuring we catch relevant items
                    results = storage.search_entries(session_id, query=q, limit=10)
                    all_results.extend(results)
        
        # 3. FALLBACK: Only if intent is 'chat' or explicitly requested do we fetch recent context blindly.
        # If intent is 'personal_recall' or 'general_info' and we found NOTHING, 
        # we return EMPTY string so the AI knows there is no record.
        if not all_results and not date_range and intent == "chat":
             # Fetch last 10 entries regardless of content
             recent = storage.get_recent_entries(session_id, limit=10)
             all_results.extend(recent)

        # Deduplicate by ID
        seen_ids = set()
        unique_results = []
        for r in all_results:
            if r['id'] not in seen_ids:
                seen_ids.add(r['id'])
                unique_results.append(r)

        # Sort by timestamp desc
        unique_results.sort(key=lambda x: x['timestamp'], reverse=True)

        # Format context
        if not unique_results:
            return ""

        context_str = "RELEVANT MEMODIARY ENTRIES:\n"
        for r in unique_results:
            # Include 'text' and 'type' (user/model) to give context on who said what
            # r['type'] might not be in the dict returned by search_entries depending on storage impl.
            # Assuming search_entries returns full dicts.
            role_label = "ME" if r.get('role') == 'user' else "YOU"
            context_str += f"- [{r['timestamp']}] {role_label}: {r['text']}\n"
        
        return context_str

# Global instance
query_engine = QueryEngine()
