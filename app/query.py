import os
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple
from app.storage import storage
from app.key_manager import key_manager
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
You are a MemoDiary Query Analyzer. Your job is to accurately determine the user's intent to route the query to the correct data source (Personal Memory vs General World Knowledge).

INTENTS:
1. "personal_recall": The user is asking about THEIR OWN life, past logs, health, work, or feelings.
   - Triggers: "I", "my", "we", "yesterday", "last week", "remember", "what did I do".
   - Example: "What did I eat yesterday?" (Requires DB Search)
   - Example: "When is my meeting?" (Requires DB Search)
2. "general_info": The user is asking about objective facts, definitions, math, coding, or world events.
   - Triggers: "Who is", "What is", "Calculate", "Weather in", "Translate", "Python code".
   - Example: "Who won the World Cup?" (NO DB Search needed, trust your knowledge)
   - Example: "How do I center a div?" (NO DB Search needed)
3. "mixed": The user connects a personal event to a general concept.
   - Example: "I visited the Eiffel Tower. How tall is it?" (Needs memory of visit + fact about height).
4. "chat": greeting, closure, or small talk with no specific information retrieval need.
   - Example: "Hi", "Good morning", "You are cool".
5. "confirmation": The user is agreeing/disagreeing to a system request (e.g. "Yes save that").

EXTRACTION RULES:
- **reasoning**: A brief explanation of WHY you chose this intent.
- **search_queries**: Keywords to search in the DIARY (Only for personal/mixed).
- **general_query**: If intent is "general_info" or "mixed", extract the question for the LLM.
- **date_range**: Start and end dates if specified.
- **filter_event_type**: If query matches specific categories: [birthday, interview, travel, health, work, relationship].
- **is_sensitive_event**: true if text mentions Life Events (Health, Accident, Job, Death).

Output format (JSON only):
{
  "reasoning": "User is asking about their own past action ('what did I do').",
  "intent": "personal_recall" | "general_info" | "mixed" | "chat",
  "search_queries": ["keyword1"],
  "general_query": "Question text" | null,
  "date_range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" } | null,
  "is_sensitive_event": true | false,
  "filter_event_type": "birthday" | null,
  "language_code": "en"
}
"""

class QueryEngine:
    def __init__(self):
        # We don't init client once anymore, we create per request or rotate
        pass

    def _get_client(self):
        key = key_manager.get_next_key()
        if key:
            return genai.Client(api_key=key, http_options={'api_version': 'v1alpha'})
        return None

    async def analyze_query(self, text: str, current_time: str) -> Dict[str, Any]:
        """
        Determine if query needs context retrieval.
        """
        full_prompt = f"Current Time Reference: {current_time}\nInput: {text}"
        
        client = self._get_client()
        if not client:
            return {"intent": "chat", "search_queries": []}

        try:
            # UPGRADE: Use Flash-Lite for Ultra-Low Latency Classification
            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash-lite-preview-02-05",
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

    def retrieve_context(self, session_id: str, search_queries: List[str], date_range: Dict[str, str] = None, intent: str = "chat", filter_event_type: str = None) -> str:
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

        # 2. Search by event type explicitly (Optimization)
        if filter_event_type:
            # If we have a specific event type, we prioritize fetching those
            results = storage.search_entries(session_id, event_type=filter_event_type, limit=20)
            all_results.extend(results)

        # 3. Search by keywords
        if search_queries:
            for q in search_queries:
                if q: # guard against empty strings
                    # Increase limit to ensuring we catch relevant items
                    # Pass event_type if we have it to narrow down keyword search too
                    results = storage.search_entries(session_id, query=q, event_type=filter_event_type, limit=10)
                    all_results.extend(results)
        
        # 4. FALLBACK: Only if intent is 'chat' or explicitly requested do we fetch recent context blindly.
        if not all_results and not date_range and not filter_event_type and intent == "chat":
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
            role_label = "ME" if r.get('role') == 'user' else "YOU"
            timestamp = r['timestamp']
            text = r['text']
            # Optional: Show event type if relevant
            meta = ""
            if r.get("event_type"): meta = f"[{r['event_type']}] "
            
            context_str += f"- [{timestamp}] {meta}{role_label}: {text}\n"
        
        return context_str

# Global instance
query_engine = QueryEngine()
