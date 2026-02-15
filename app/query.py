import os
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple
from app.storage import storage
from app.key_manager import key_manager
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime, timedelta

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
You are a Query Router. Your job is to classify the user's question into ONE category and provide the specific routing parameters.

**CATEGORIES**:
1. **personal_fact**: User asks for a specific static fact OR asks if you remember a specific detail/topic (e.g., "What is my dog's name?", "Do you remember my project?", "What is my favorite color?"). **PRIORITIZE THIS** if the user asks "Do you remember X?", even if they mention "yesterday" or "last time".
2. **date_recall**: User asks about a specific time range or date (e.g., "What did I do yesterday?", "Summary of last 6 months?", "Last week overview").
3. **emotional_recall**: User asks about recent feelings or needs context from the immediate conversation (e.g., "Why was I sad?", "What did we just talk about?", "Hi", "How are you?").
4. **planning**: User asks for a plan, itinerary, suggestion, or advice based on their life (e.g., "Plan a trip to London", "Give me a diet plan", "How can I improve my routine?").
5. **general_knowledge**: User asks about world facts, math, code, or definitions (e.g., "Who is Obama?", "Python help").
6. **confirmation**: User is explicitly agreeing/disagreeing to a previous system request (e.g., "Yes please", "No don't save that", "Sure").
7. **trend_analysis**: User asks to compare metrics or track changes over time (e.g., "How is my energy compared to last week?", "Am I sleeping better?", "Graph my stress").
8. **data_review**: User asks to see, review, or audit what the AI knows (e.g., "What do you know about me?", "List my facts", "Show my profile").

**OUTPUT FORMAT (JSON)**:
{
  "intent": "personal_fact" | "date_recall" | "emotional_recall" | "planning" | "general_knowledge" | "confirmation" | "trend_analysis" | "data_review",
  "memory_keys": ["key1", "key2"],  // For 'personal_fact'. Use snake_case if possible.
  "start_date": "YYYY-MM-DD" | null, // For 'date_recall' or 'trend_analysis'.
  "end_date": "YYYY-MM-DD" | null,   // For 'date_recall' or 'trend_analysis'.
  "metrics": ["energy", "stress", "sleep"], // For 'trend_analysis' (which metrics to compare).
  "reasoning": "brief explanation",
  "language_code": "en",
  "is_sensitive": boolean
}

**EXAMPLES**:

Input: "Plan a trip to Goa for me."
Output: { "intent": "planning", "memory_keys": [], "reasoning": "User wants a travel itinerary", "is_sensitive": false }

Input: "Are my energy levels improving since last month?"
Output: { "intent": "trend_analysis", "metrics": ["energy"], "start_date": "2026-06-01", "end_date": "2026-07-01", "reasoning": "Comparing energy trend", "is_sensitive": false }

Input: "What do you know about me?"
Output: { "intent": "data_review", "reasoning": "Privacy audit request", "is_sensitive": false }

Input: "Do you remember the project details I mentioned earlier?"
Output: { "intent": "personal_fact", "memory_keys": ["project", "project_details"], "reasoning": "User asks for specific topic memory", "is_sensitive": false }
"""


import re

class QueryRouting:
    TRIVIAL = "trivial"
    WORLD = "world"
    GENERAL = "general"
    PERSONAL = "personal"

def fast_intent_check(text: str) -> dict:
    """
    Ultra-fast rule-based router (Regex/Keyword).
    Returns: { "intent": "trivial|world|general|personal", "payload": ... }
    """
    text = text.strip()
    text_lower = text.lower()
    
    # 1. TRIVIAL: Math
    # Simple arithmetic: 2 + 2, 5*10, 100/4
    # Regex allows spaces
    math_match = re.match(r'^(\d+)\s*([\+\-\*\/])\s*(\d+)$', text)
    if math_match:
        try:
            n1 = float(math_match.group(1))
            op = math_match.group(2)
            n2 = float(math_match.group(3))
            res = 0
            if op == '+': res = n1 + n2
            elif op == '-': res = n1 - n2
            elif op == '*': res = n1 * n2
            elif op == '/': res = n1 / n2 if n2 != 0 else "undefined"
            
            # Format nicely
            if isinstance(res, float) and res.is_integer():
                res = int(res)
            return {"intent": QueryRouting.TRIVIAL, "payload": str(res)}
        except:
            pass

    # 2. TRIVIAL: Greetings (Simple) - return empty payload implies "let AI handle quickly" 
    if text_lower in ["hi", "hello", "hey", "test", "ping"]:
        return {"intent": QueryRouting.TRIVIAL, "payload": None}

    # 3. PERSONAL: Keywords
    personal_keywords = [
        r"\bmy\b", r"\bme\b", r"\bi\b", r"\bi'm\b", r"\bremember\b", r"\brecall\b", 
        r"\byesterday\b", r"\blast\s+(week|month|year|night)\b", r"\bwe\b", r"\bour\b",
        r"\bdiary\b", r"\bentry\b", r"\bnote\b"
    ]
    for pk in personal_keywords:
        if re.search(pk, text_lower):
            return {"intent": QueryRouting.PERSONAL}

    # 4. WORLD: Keywords
    world_keywords = [
        r"\bwho\s+is\b", r"\bwhat\s+is\b", r"\bwhere\s+is\b", 
        r"\bnews\b", r"\bweather\b", r"\bevent(s)?\b", r"\bcapital\b",
        r"\bpopulation\b", r"\bpresident\b", r"\bmeaning\b", r"\bdefine\b"
    ]
    for wk in world_keywords:
        if re.search(wk, text_lower):
            return {"intent": QueryRouting.WORLD}

    # 5. GENERAL: Fallback
    return {"intent": QueryRouting.GENERAL}

class QueryEngine:
    def __init__(self):
        pass

    def _get_client(self):
        key = key_manager.get_next_key()
        if key:
            return genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
        return None

    async def analyze_query(self, text: str, current_time: str) -> Dict[str, Any]:
        """
        Determine if query needs context retrieval.
        """
        full_prompt = f"Current Time: {current_time}\nInput: {text}"
        
        # FAST PATH: Check for greetings to skip expensive analysis
        import re
        # Matches: "Hi", "Hello", "Hey", "Hi there", "Good morning" (case insensitive)
        greeting_pattern = r"^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening)|hola|namaste)(\s+(there|memo|friend))?[\W]*$"
        if len(text) < 30 and re.match(greeting_pattern, text.strip(), re.IGNORECASE):
             safe_print(f"[FAST PATH] Greeting detected: '{text}' -> Skipping Analysis LLM")
             return {"intent": "chat", "language_code": "en", "is_sensitive": False}

        client = self._get_client()
        if not client:
            return {"intent": "emotional_recall", "language_code": "en", "is_sensitive": False}

        try:
            # UPGRADE: Use Flash-Lite/Flash for latency
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
            safe_print(f"Query Analysis Error: {e}")
            # Fallback
            return {"intent": "emotional_recall", "language_code": "en", "is_sensitive": False}

    def retrieve_context(self, session_id: str, analysis: Dict[str, Any]) -> str:
        """
        Fetch relevant entries/facts based on analysis.
        """
        intent = analysis.get("intent")
        
        context_str = ""
        
        # ROUTE 1: Personal Fact -> Query Memory Index
        if intent == "personal_fact":
             # 1. Fetch Authoritative Profile Data
             user_profile = storage.get_user(session_id)
             profile_name = user_profile.get('name') if user_profile else None
             profile_age = user_profile.get('age') if user_profile else None
             
             # 2. Add Profile Context FIRST (The Truth)
             if profile_name or profile_age:
                 context_str += "VERIFIED USER PROFILE (PRIORITY):\n"
                 if profile_name: context_str += f"- Name: {profile_name}\n"
                 if profile_age: context_str += f"- Age: {profile_age}\n"
             
             # 3. Fetch Memory Fragments
             keys = analysis.get("memory_keys", [])
             if keys:
                 # NORMALIZATION: Snake case for better matching
                 normalized_keys = []
                 for k in keys:
                     normalized_keys.append(k)
                     normalized_keys.append(k.replace(" ", "_")) # Add snake_case variant
                     if "_" in k:
                         normalized_keys.append(k.replace("_", " ")) # Add space variant
                 
                 # Remove duplicates
                 final_keys = list(set(normalized_keys))
                 
                 # BATCH QUERY OPTIMIZATION: Fetch all keys in one go
                 found_facts = storage.get_memory_items_batch(session_id, final_keys)
                 
                 if found_facts:
                     context_str += "OTHER RELEVANT FACTS:\n"
                     for f in found_facts:
                         # CRITICAL: Skip conflicting Name/Age keys if we already have them in Profile
                         k_lower = f['memory_key'].lower()
                         if profile_name and k_lower in ['name', 'user_name', 'my_name', 'first_name']:
                             continue
                         if profile_age and k_lower in ['age', 'user_age', 'my_age']:
                             continue
                             
                         context_str += f"- {f['memory_key']}: {f['memory_value']} (Confidence: {f['confidence']})\n"
                 else:
                     if not (profile_name or profile_age):
                        context_str += "No specific personal facts found for this query.\n"

        # ROUTE 2: Date Recall -> Query Multi-Level Summaries
        elif intent == "date_recall":
            start_date = analysis.get("start_date")
            end_date = analysis.get("end_date") or start_date
            
            if start_date:
                # Calculate duration in days
                try:
                    d1 = datetime.strptime(start_date, "%Y-%m-%d")
                    d2 = datetime.strptime(end_date, "%Y-%m-%d")
                    duration = (d2 - d1).days
                except:
                    duration = 0
                
                context_str += f"RECALLING FOR RANGE: {start_date} to {end_date} ({duration + 1} days)\n"

                # Sub-Route A: Long Duration (> 30 days) -> Use Monthly Summaries
                if duration > 30:
                    # Logic: fetch monthly summaries that overlap/fall in this range.
                    # MVP: Just fetch last 6 months summaries
                    context_str += "MONTHLY SUMMARIES (High Level):\n"
                    summaries = storage.get_monthly_summaries(session_id, limit=6)
                    for s in summaries:
                        context_str += f"- Month {s['month']}: {s['summary']} ({s['dominant_mood']})\n"

                # Sub-Route B: Medium Duration (> 6 days) -> Use Weekly Summaries
                elif duration > 6:
                     context_str += "WEEKLY SUMMARIES:\n"
                     summaries = storage.get_weekly_summaries(session_id, limit=4)
                     for s in summaries:
                         context_str += f"- Week {s['start_date']}: {s['summary']} ({s['dominant_mood']})\n"

                # Sub-Route C: Short Duration -> Use Daily Summaries
                else:
                    # MVP: Just check start_date summary
                    summary = storage.get_daily_summary(session_id, start_date)
                    if summary:
                        context_str += f"SUMMARY FOR {start_date}:\n"
                        context_str += f"Overview: {summary['summary']}\n"
                        context_str += f"Mood: {summary['dominant_mood']}\n"
                    else:
                         context_str += f"No summary found for {start_date}. Checking raw entries...\n"
                         entries = storage.get_entries_in_range(session_id, f"{start_date}T00:00:00", f"{start_date}T23:59:59")
                         if entries:
                             for e in entries:
                                 context_str += f"- [{e['timestamp']}] {e['text']}\n"
                         else:
                             context_str += "No entries found for this date.\n"

        # ROUTE 3: Planning -> Inject Topic Profiles + RECENT CONTEXT (Multi-Factor)
        elif intent == "planning":
             # 1. Long Term Profiles
             topics = ["health", "food", "routine", "preferences", "work"]
             profiles = storage.get_topic_states(session_id, topics)
             
             if profiles:
                 context_str += "CURRENT LIFE PROFILE (Relevance: HIGH):\n"
                 for topic, state in profiles.items():
                     context_str += f"- {topic.upper()}: {state}\n"
             else:
                 context_str += "No specific life profile data found yet (e.g. Health, Food).\n"

             # 2. Basic Profile
             user_profile = storage.get_user(session_id)
             if user_profile:
                 context_str += f"User: {user_profile.get('name')} ({user_profile.get('age')})\n"
            
             # 3. [NEW] IMMEDIATE CONTEXT (Audit: Multi-Factor) - Check if user is tired right NOW
             recent_text = storage.get_recent_context(session_id, limit=10)
             context_str += f"\nRECENT CONTEXT (Last 10 msgs - CHECK FOR IMMEDIATE CONSTRAINTS):\n{recent_text}\n"

        # ROUTE 4: Trend Analysis (Audit: Temporal Trends)
        elif intent == "trend_analysis":
            metrics = analysis.get("metrics", ["energy", "stress"])
            # Default to last 30 days if no date
            end_d = datetime.now()
            start_d = end_d - timedelta(days=30)
            
            s_date = analysis.get("start_date") or start_d.strftime("%Y-%m-%d")
            e_date = analysis.get("end_date") or end_d.strftime("%Y-%m-%d")
            
            context_str += f"ANALYZING TRENDS ({', '.join(metrics)}) from {s_date} to {e_date}:\n"
            
            data_points = storage.get_daily_metrics_range(session_id, s_date, e_date)
            if data_points:
                for dp in data_points:
                    line_parts = [f"Date: {dp['date']}"]
                    for m in metrics:
                        val = dp.get(m)
                        if val is not None and val != -1:
                            line_parts.append(f"{m.capitalize()}: {val}/10")
                    context_str += " | ".join(line_parts) + "\n"
            else:
                context_str += "No numeric data found for this period to graph.\n"

        # ROUTE 5: Data Review (Audit: Privacy Control)
        elif intent == "data_review":
            context_str += "=== CONFIDENTIAL USER DATA REPORT ===\n"
            
            # Profile
            user = storage.get_user(session_id)
            if user:
                context_str += f"PROFILE: Name={user['name']}, Age={user['age']}\n\n"
            
            # Key Facts
            facts = storage.get_memory_items(session_id) # Fetches recent cache or all? Logic in storage limits it effectively
            if facts:
                context_str += "STORED FACTS (Sample):\n"
                for f in facts[:15]: # Limit to avoid context overflow
                    context_str += f"- [{f['memory_type']}] {f['memory_key']}: {f['memory_value']}\n"
            
            # Topic States
            topics = storage.get_topic_states(session_id)
            if topics:
                context_str += "\nLIFE CONTEXT SNAPSHOTS:\n"
                for t, s in topics.items():
                    context_str += f"- {t.upper()}: {s}\n"
            
            context_str += "\nSYSTEM NOTE: Present this transparently to the user."

        # ROUTE 6: Emotional/Recent Recall & Confirmation & Chat -> Query Recent Entries
        elif intent in ["emotional_recall", "confirmation", "chat"]:
            recent_text = storage.get_recent_context(session_id, limit=10)
            context_str += f"RECENT CONVERSATION:\n{recent_text}\n"

        # ROUTE 7: General Knowledge -> Do Nothing (Empty Context)
        elif intent == "general_knowledge":
            pass 

        return context_str

# Global instance
query_engine = QueryEngine()
