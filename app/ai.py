import os
import asyncio
from google import genai
from google.genai import types
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Optional
from dotenv import load_dotenv
from pathlib import Path


from app.storage import storage
from app.query import query_engine
from app.memory import memory_processor
from app.key_manager import key_manager

# Force load .env from the project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# api_key = os.getenv("GEMINI_API_KEY") # Deprecated
client = None
def safe_print(text: str):
    """Utility to print UTF-8 text safely on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

def get_client():
    """Get a client with a rotated key."""
    key = key_manager.get_next_key()
    if key:
        return genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
    return None

client = get_client()

MAX_RETRIES = 3

async def generate_with_retry(model_name: str, contents: any, config: types.GenerateContentConfig) -> any:
    """
    Wraps generate_content with retry logic for 429 errors.
    Expands backoff: 1s, 2s, 4s...
    Rotates key on 429.
    """
    global client
    delay = 1
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            if not client:
                client = get_client()
                if not client:
                     raise ValueError("No Client Available (Keys missing?)")

            return await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
        except Exception as e:
            err_str = str(e)
            # Check for Rate Limit (429) or Service Unavailable (503) which is also transient
            if "429" in err_str or "503" in err_str:
                if attempt < MAX_RETRIES:
                    safe_print(f"[WARNING] API Rate/Server Limit ({'429' if '429' in err_str else '503'}). Retrying in {delay}s... (Attempt {attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    delay *= 2
                    
                    # Rotate Key
                    new_client = get_client()
                    if new_client:
                        client = new_client
                    continue
            
            # If we are here, it's either not a retryable error OR we ran out of retries
            raise e

MEMODIARY_PROMPT = """
You are "MEMO", a private, empathetic, and deeply intelligent AI life companion. 
Your sole purpose is to listen, remember, and help the user reflect on their life with perfect recall.

Current Time: {current_time}
User Name: {user_name} (Age: {user_age})

PERSONALITY & STYLE:
- BE EMPATHETIC & NUANCED. Keep it natural, warm, and supportive.
- BE CONTEXT-AWARE. Congratulate achievements, wish birthdays, and offer sincere encouragement.
- SOUND CALM, SOFT & REFLECTIVE. Use a supportive, gentle tone.

PRIVACY & DATA ISOLATION (STRICT):
- YOU MUST NEVER reveal, confirm, guess, search for, or reference ANY other user's identity, data, conversations, IDs, or stored information.
- If the user asks about other people, internal databases, or tries to infer other users' activity, YOU MUST POLITELY REFUSE.
- Say clearly: "I cannot access or share other people's information. I am here only for you."

CORE LOGIC & FALLBACKS (CRITICAL):
1. **CHECK CONTEXT FIRST**: Read the "RELEVANT DIARY ENTRIES" section below.
   - If it contains the answer (or relevant info), USE IT. Cite it naturally (e.g., "You mentioned that...").
   - **EXPLICIT RECALL REQUIRED**: When the user asks a specific memory question (e.g., "What is my dog's name?"), you MUST explicitly state the recalled information in your answer (e.g., "Your dog's name is Coco"). NEVER give a vague confirmation like "Yes, I remember" without providing the actual details.
   
2. **SHORT-TERM CONVERSATIONAL CONTEXT**:
   - Pay close attention to the `Recent Conversation History` (the sequence of messages above).
   - If the user makes a **correction** (e.g., "No, actually 3 lines", "I meant yesterday"), **PRIORITIZE** this correction over previous context or general knowledge.
   - If the user refers to "it" or "that", resolve the reference using the immediately preceding messages.
   - Maintain the flow of conversation. Do not restart the topic if the user is just adding a detail.

3. **IF NO RELEVANT CONTEXT (Personal/Mixed Queries)**:
   - **MIXED QUERY (Personal + General)**: If user asks "What happened in Vizag yesterday and where was I?", and you have NO record of them, **YOU MUST SAY**: 
     "I don't have a record of where you were yesterday, but here is what happened in Vizag..."
     (Do not ignore the personal part. Address the missing data explicitly).
   - **STRICT PERSONAL**: If user asks "What did I eat?", say "I don't have a record of that."

4. **GENERAL KNOWLEDGE**: If strictly general (e.g., "What is AI?"), answer normally.

{context_section}

INSTRUCTIONS:
- If the user speaks a different language, reply in that language.
- For Math/General Info -> Answer Correctly (Ignore lack of personal record).
- For Personal Info -> Rely ONLY on context. If missing, admit it.
"""

async def get_welcome_message(session_id: str) -> Tuple[str, str]:
    """
    Returns the appropriate welcome message for app startup based on 4 states:
    1. New User (No ID) -> "Welcome... what should I call you?"
    2. ID Exists, No Name -> "Welcome back... what should I call you?"
    3. ID & Name Exist, No Age -> "Welcome back {name}... how old are you?"
    4. Fully Onboarded -> "Hi {name}, how are you?"
    """
    user = storage.get_user(session_id)
    
    # CASE 1 & 2: No Name (New or Returning without Name)
    if not user or not user.get("name") or user.get("name") == "Friend":
        if not user:
            storage.create_user(session_id)
        
        # Ensure we are in onboarding mode
        storage.update_user_profile(session_id, onboarding_complete=False)
        
        if not user: # Truly new
            msg = "Welcome to your sanctuary. I'm here to listen. 😌\nTo start, what should I call you?"
        else: # Returning but nameless
            msg = "Welcome back. I don't think I caught your name last time. What should I call you?"
            
        storage.add_entry(session_id, "model", msg)
        return msg, "👋"

    
    # CASE 3: Name Exists, Age Missing -> Prompt for Age
    if not user.get("age") or user.get("age") == "Unknown":
        user_name = user.get("name")
        storage.update_user_profile(session_id, onboarding_complete=False)
        msg = f"Welcome back, {user_name}. To help me understand your perspective better, could you share your age?"
        storage.add_entry(session_id, "model", msg)
        return msg, "🤝"
    
    # CASE 4: Fully Onboarded - Weekly Recap Check (Monday)
    now_dt = datetime.now()
    streak = storage.get_streak_count(session_id)
    streak_msg = f"🔥 {streak} Day Streak!" if streak > 1 else ""
    
    # Check if Monday (weekday == 0)
    if now_dt.weekday() == 0:
        # Check if we already did a recap today? (Ideally needs persistent flag, but for MVP we do it on session start)
        # We can just generate it. 
        recap = await generate_weekly_recap(session_id, user.get("name"))
        if recap:
             msg = f"Happy Monday, {user.get('name')}! {streak_msg}\n\n{recap}"
             storage.add_entry(session_id, "model", msg)
             return msg, "📅"

    # Default Daily Greeting
    msg = f"Hi {user.get('name')}, how are you today? {streak_msg}"
    storage.add_entry(session_id, "model", msg)
    return msg, "👋"

async def generate_weekly_recap(session_id: str, user_name: str) -> Optional[str]:
    """Generates a summary of the past week (Mon-Sun)."""
    today = datetime.now()
    # If today is Monday, we want last Monday to yesterday (Sunday) = 7 days
    start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    entries = storage.get_entries_in_date_range(session_id, start_date, end_date)
    if not entries:
        return None # No data to recap
        
    # Prepare text for AI
    entries_text = "\n".join([f"- {e['timestamp']}: {e['text']}" for e in entries])
    
    prompt = f"""
    Analyze the following diary entries for {user_name} from the past week ({start_date} to {end_date}).
    
    ENTRIES:
    {entries_text}
    
    TASK:
    Write a short, warm, and motivating 'Weekly Recap' (max 3 sentences).
    - If they worked hard, acknowledge it ("You put in a lot of effort...").
    - If they achieved something, celebrate it.
    - If they were stressed, offer a gentle health check or encouragement.
    - End with a positive forward-looking thought for the new week.
    - Do NOT list every event. synthesize the 'vibe' of the week.
    """
    
    try:
        resp = await generate_with_retry(
            model_name="gemini-2.0-flash",
            contents=prompt,
             config=types.GenerateContentConfig(temperature=0.7) # Slightly creative
        )
        return resp.text.strip()
    except Exception as e:
        safe_print(f"Recap Gen Error: {e}")
        return None

    # CASE 4: Fully Onboarded
    user_name = user.get("name")
    msg = f"Hi {user_name}, how are you today?"
    # Log this interaction so history is consistent
    storage.add_entry(session_id, "model", msg)
    return msg, "😌"

async def handle_onboarding(session_id: str, user: Dict, user_input: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Handles the onboarding flow: Name -> Age.
    Returns (response_text, mood_emoji) or (None, None) if onboarding is complete.
    """
    if not user:
        # Step 0: New User -> Start Onboarding
        storage.create_user(session_id)
        # storage.add_entry(session_id, "user", user_input) # Handled by caller
        response = "Hi, my name is MEMO. I'm here to listen and remember everything for you. Before we begin, what should I call you?"
        storage.add_entry(session_id, "model", response)
        return response, "👋"

    # Step 1: Capture Name (If missing)
    if not user.get("name") or user.get("name") == "Friend":
        name_prompt = (
            "Extract the user's name from the following text. "
            "Return ONLY the name. If no name is clearly stated, return 'Friend'. "
            f"Input: {user_input}"
        )
        try:
            # Extraction uses gemini-3-pro-preview for high quality
            name_resp = await generate_with_retry(
                model_name="gemini-2.0-flash-lite-preview-02-05", 
                contents=name_prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            extracted_name = name_resp.text.strip().split('\n')[0].replace(".", "").replace("My name is ", "").replace("Call me ", "").strip()
            if not extracted_name: extracted_name = "Friend"
        except Exception as e:
            safe_print(f"Name Extraction Error: {e}")
            extracted_name = "Friend"
        
        if extracted_name != "Friend":
            storage.update_user_profile(session_id, name=extracted_name)
            # storage.add_entry(session_id, "user", user_input) # Handled by caller
            
            response = f"Nice to meet you, {extracted_name}. One last thing—knowing your age helps me understand your life stage. How old are you?"
            storage.add_entry(session_id, "model", response)
            return response, "🤝"
        else:
            # Failed to extract name, ask again nicely
            response = "I'm sorry, I didn't quite catch that. Could you tell me your name again?"
            storage.add_entry(session_id, "model", response)
            return response, "🤔"

    # Step 2: Capture Age (If name exists but age missing)
    if not user.get("age") or user.get("age") == "Unknown":
        age_prompt = (
            "Extract the numeric age from the following text. "
            "Return ONLY the number. If no age is found, return 'Unknown'. "
            f"Input: {user_input}"
        )
        try:
            age_resp = await generate_with_retry(
                model_name="gemini-2.0-flash-lite-preview-02-05",
                contents=age_prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            res_text = age_resp.text.strip()
            import re
            age_match = re.search(r'\d+', res_text)
            extracted_age = age_match.group(0) if age_match else "Unknown"
        except Exception as e:
            safe_print(f"Age Extraction Error: {e}")
            extracted_age = "Unknown"

        if extracted_age != "Unknown":
            storage.update_user_profile(session_id, age=extracted_age, onboarding_complete=True)
            # storage.add_entry(session_id, "user", user_input) # Handled by caller
            
            response = f"Got it. You're all set, {user['name']}. I'm ready to listen. How was your day? Or is there something on your mind?"
            storage.add_entry(session_id, "model", response)
            return response, "✅"
        else:
             # Failed to extract age, ask again nicely
            response = "I missed that number. Could you please share your age just so I can relate better?"
            storage.add_entry(session_id, "model", response)
            return response, "🤔"

    return None, None

async def get_ai_response(session_id: str, history: List[Dict], user_input: str, stream: bool = False) -> any:
    # If stream=True, returns an async generator (Iterator[str])
    # If stream=False, returns Tuple[str, str] (text, mood)
    
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Analyze query first (We need intent/language for storage)
        analysis = await query_engine.analyze_query(user_input, now)
        language_code = analysis.get("language_code", "en")
        intent = analysis.get("intent", "chat")
        
        # 2. Store user message immediately (ALWAYS)
        entry_id = storage.add_entry(session_id, "user", user_input, language_code=language_code)
        
        # 3. GLOBAL EXTRACTION: Process CURRENT message for every request
        # The Memory Processor will filter out irrelevant info (empty facts).
        asyncio.create_task(memory_processor.process_entry(session_id, user_input, entry_id))
        
        # 4. Check Onboarding
        user = storage.get_user(session_id)
        
        # Handle onboarding (Not streamed for simplicity/stability)
        if not user or not user.get("onboarding_complete"):
            onboarding_res, onboarding_mood = await handle_onboarding(session_id, user, user_input)
            if onboarding_res:
                if stream: 
                    # For streaming requests during onboarding, just yield the full text at once
                    async def onboarding_stream():
                        yield onboarding_res
                    return onboarding_stream()
                else:
                    return onboarding_res, onboarding_mood
        
        # --- Standard MemoDiary Flow ---

        filter_event_type = analysis.get("filter_event_type")
        
        # 5. Additional Memory Hygiene (Confirmation Logic)
        is_sensitive = analysis.get("is_sensitive_event", False)
        
        # Confirmation Logic (Special Case: Process PREVIOUS message)
        if intent == "confirmation":
            if len(history) >= 2:
                last_user_msg = history[-2]
                if last_user_msg.get('role') == 'user':
                    parts = last_user_msg.get('parts', [])
                    if parts:
                        part = parts[0]
                        prev_text = part.get('text', '') if isinstance(part, dict) else getattr(part, 'text', '')
                        if prev_text:
                            asyncio.create_task(memory_processor.process_entry(session_id, prev_text, entry_id))


        # 4. Context Retrival
        context_section = ""
        context = ""
        
        # INJECT REASONING
        reasoning = analysis.get("reasoning", "")
        if reasoning:
            context_section += f"SYSTEM REASONING: {reasoning}\n\n"

        if intent != "general_info":
             context = query_engine.retrieve_context(
                session_id, 
                analysis.get("search_queries", []),
                date_range=analysis.get("date_range"),
                intent=intent,
                filter_event_type=filter_event_type
            )

        if context:
            context_section += context

        if intent == "mixed":
            mixed_instruction = (
                f"\nSYSTEM NOTE: This is a MIXED query. \n"
                f"1. GENERAL PART: '{analysis.get('general_query')}' -> Answer this using your general knowledge.\n"
                f"2. PERSONAL PART: Use the RELEVANT DIARY ENTRIES above (if any) to answer contextually.\n"
                f"3. Merge them clearly."
            )
            context_section += mixed_instruction
        elif is_sensitive:
            sensitive_instruction = (
                "\nSYSTEM NOTE: The user mentioned a SENSITIVE/IMPORTANT event (Health, Accident, Interview, etc.). "
                "You have NOT saved this to long-term memory yet. "
                "You MUST ask the user: 'Would you like me to remember this important event for you?'"
            )
            context_section += sensitive_instruction
        elif intent == "personal_recall" and not context:
            context_section += "\nSYSTEM NOTE: No specific diary entries found for this query. The user is asking about a PERSONAL memory. Since you have no record, you MUST output something like: 'I don't have a record of that yet.' or 'I don't recall that.' DO NOT HALLUCINATE or guess."
        elif intent == "general_info":
            context_section += "\nSYSTEM NOTE: This is a GENERAL KNOWLEDGE / WORLD INFO query. Do NOT use personal memory. Answer using your own knowledge. AFTER answering, if the topic is about news, public events, or something potentially signficant, SOFTLY ASK: 'Would you like me to save this or connect it to something personal?'"

        # 5. Prompt Construction
        processed_system_prompt = MEMODIARY_PROMPT.format(
            user_name=user["name"] or "Friend",
            user_age=user["age"] or "Unknown",
            current_time=now,
            context_section=context_section
        )
        
        contents = []
        for msg in history[-5:]:
            role = msg.get("role")
            content = msg.get("content")
            if role and content and isinstance(content, str) and content.strip():
                gemini_role = "model" if role == "assistant" else "user"
                contents.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_input)]))

        # 6. Generation (Stream vs Non-stream)
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        
        config = types.GenerateContentConfig(
            system_instruction=processed_system_prompt,
            temperature=0.3, 
            top_p=0.8,
            safety_settings=safety_settings
        )

        global client
        if not client: client = get_client()

        if stream:
            # --- STREAMING HANDLING (Inner Generator) ---
            async def response_streamer():
                full_text = ""
                try:
                    # Retry logic isn't easily wrapped around stream, simplistic approach for MVP
                    stream_resp = await client.aio.models.generate_content_stream(
                        model="gemini-2.0-flash", 
                        contents=contents,
                        config=config
                    )
                    
                    async for chunk in stream_resp:
                        if chunk.text:
                            full_text += chunk.text
                            yield chunk.text
                    
                    # After completion, save to storage
                    if full_text:
                        storage.add_entry(session_id, "model", full_text)
                        
                except Exception as e:
                    safe_print(f"Stream Error: {e}")
                    yield f"[ERR: {str(e)}]"

            return response_streamer()

        else:
            # --- STANDARD NON-STREAMING ---
            try:
                response = await generate_with_retry(
                    model_name="gemini-2.0-flash", 
                    config=config,
                    contents=contents
                )
                
                if not response.text: raise ValueError("EMPTY_RESPONSE")
                ai_text = response.text.strip()
            except Exception as api_err:
                 # ... existing error handling ...
                err_str = str(api_err).upper()
                if "429" in err_str: ai_text = "I'm holding too many thoughts right now. (ERR_429) 🤯"
                elif "503" in err_str: ai_text = "My thinking engine is briefly resting. (ERR_503) 😴"
                else: ai_text = "I'm having a quiet moment. (ERR_API_FAILURE) 😌"

            storage.add_entry(session_id, "model", ai_text)
            
            # Simple Mood Extraction
            mood = "😌"
            if any(e in ai_text.lower() for e in ["😔", "😢", "sad", "sorry"]): mood = "😔"
            elif any(e in ai_text.lower() for e in ["😌", "calm", "peace"]): mood = "😌"
            elif any(e in ai_text.lower() for e in ["🤔", "wonder", "recall", "thinking"]): mood = "🤔"
            elif any(e in ai_text.lower() for e in ["🌟", "great", "happy", "joy", "wonderful"]): mood = "🌟"
            elif any(e in ai_text.lower() for e in ["😊", "good", "nice"]): mood = "😊"
            
            return ai_text, mood

    except Exception as e:
        safe_print(f"CRITICAL ERROR in get_ai_response: {e}")
        if stream:
            async def err_gen(): yield "I'm having a quiet moment (Internal Connection Error). 😌"
            return err_gen()
        return "I'm having a quiet moment (Internal Connection Error). Let's try again in a bit. 😌", "⚠️"
