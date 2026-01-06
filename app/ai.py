import os
import asyncio
from google import genai
from google.genai import types
from datetime import datetime
from typing import Tuple, List, Dict, Optional
from dotenv import load_dotenv
from pathlib import Path

from app.storage import storage
from app.query import query_engine
from app.memory import memory_processor

# Force load .env from the project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")
client = None
def safe_print(text: str):
    """Utility to print UTF-8 text safely on Windows consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

if api_key:
    client = genai.Client(
        api_key=api_key,
        http_options={'api_version': 'v1beta'}
    )

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
   
2. **IF NO RELEVANT CONTEXT (Empty or unrelated)**:
   - **GENERAL KNOWLEDGE / EVENTS / MATH**: If the user asks about the external world (e.g., "What happened in Vizag/London?", "What is 2 + 2?", "News?"), **ANSWER IT** using your own knowledge. **IGNORE** the fact that you are a diary for these questions.
   - **PERSONAL QUESTIONS**: If the user asks something strictly personal (e.g., "What is my name?", "What did I eat?", "What is my phone number?") and there is **NO** record in the context below, **YOU MUST SAY**: "I don't have a record of that yet."
   - **DO NOT HALLUCINATE**: Never invent personal details.

{context_section}

INSTRUCTIONS:
- If the user speaks a different language, reply in that language.
- For Math/General Info -> Answer Correctly (Ignore lack of personal record).
- For Personal Info -> Rely ONLY on context. If missing, admit it.
"""

async def get_welcome_message(session_id: str) -> Tuple[str, str]:
    """
    Returns the appropriate welcome message for app startup.
    - New User / No Name: "Welcome... what should I call you?"
    - Returning User: "Welcome back [Name]..."
    """
    user = storage.get_user(session_id)
    
    # CASE 1: New User or No Session ID or No Name -> Onboarding
    if not user or not user.get("name") or user.get("name") == "Friend":
        # Make sure user exists
        if not user:
            storage.create_user(session_id)
        
        # Reset/Set onboarding step
        storage.update_user_profile(session_id, onboarding_complete=False)
        
        msg = "Welcome to your sanctuary. I'm here to listen. 😌\nTo start, what should I call you?"
        storage.add_entry(session_id, "model", msg)
        return msg, "👋"

    # CASE 2: Returning User with Name -> Personalized Welcome
    user_name = user.get("name")
    msg = f"Welcome back to your sanctuary, I'm here to listen, {user_name}. 😌"
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
        storage.add_entry(session_id, "user", user_input)
        response = "Hi, my name is MEMO. I'm here to listen and remember everything for you. Before we begin, what should I call you?"
        storage.add_entry(session_id, "model", response)
        return response, "👋"

    # Step 1: Capture Name
    if not user["name"]:
        name_prompt = (
            "Extract the user's name from the following text. "
            "Return ONLY the name. If no name is clearly stated, return 'Friend'. "
            f"Input: {user_input}"
        )
        try:
            # Extraction uses gemini-3-pro-preview for high quality
            name_resp = await client.aio.models.generate_content(
                model="gemini-3-pro-preview", 
                contents=name_prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            extracted_name = name_resp.text.strip().split('\n')[0].replace(".", "").replace("My name is ", "").replace("Call me ", "").strip()
            if not extracted_name: extracted_name = "Friend"
        except Exception as e:
            safe_print(f"Name Extraction Error: {e}")
            extracted_name = "Friend"
        
        storage.update_user_profile(session_id, name=extracted_name)
        storage.add_entry(session_id, "user", user_input)
        
        response = f"Nice to meet you, {extracted_name}. One last thing—knowing your age helps me understand your life stage. How old are you?"
        storage.add_entry(session_id, "model", response)
        return response, "🤝"

    # Step 2: Capture Age
    if not user["age"]:
        age_prompt = (
            "Extract the numeric age from the following text. "
            "Return ONLY the number. If no age is found, return 'Unknown'. "
            f"Input: {user_input}"
        )
        try:
            age_resp = await client.aio.models.generate_content(
                model="gemini-3-pro-preview",
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

        storage.update_user_profile(session_id, age=extracted_age, onboarding_complete=True)
        storage.add_entry(session_id, "user", user_input)
        
        response = f"Got it. You're all set, {user['name']}. I'm ready to listen. How was your day? Or is there something on your mind?"
        storage.add_entry(session_id, "model", response)
        return response, "✅"

    return None, None

async def get_ai_response(session_id: str, history: List[Dict], user_input: str) -> Tuple[str, str]:
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. User / Session Management (Onboarding)
        user = storage.get_user(session_id)
        
        # Handle onboarding if not complete
        if not user or not user.get("onboarding_complete"):
            onboarding_res, onboarding_mood = await handle_onboarding(session_id, user, user_input)
            if onboarding_res:
                return onboarding_res, onboarding_mood

        # --- Standard MemoDiary Flow ---
        
        # 1. Analyze query & Retrieve Context (Move up to get language first)
        analysis = await query_engine.analyze_query(user_input, now)
        language_code = analysis.get("language_code", "en")
        intent = analysis.get("intent", "chat")
        
        # 2. Store user message immediately with language code
        entry_id = storage.add_entry(session_id, "user", user_input, language_code=language_code)
        
        # 2. Extract memory asynchronously (pass entry_id explicitly)
        asyncio.create_task(memory_processor.process_entry(session_id, user_input, entry_id))

        # 3. Retrieve Context
        # Pass intent so retrieve_context knows whether to fallback to recent history or not
        context = query_engine.retrieve_context(
            session_id, 
            analysis.get("search_queries", []),
            date_range=analysis.get("date_range"),
            intent=intent
        )

        context_section = ""
        if context:
            context_section = context
        elif intent == "personal_recall":
            context_section = "SYSTEM NOTE: No specific diary entries found for this query. The user is asking about a PERSONAL memory. Since you have no record, you MUST output something like: 'I don't have a record of that.' DO NOT HALLUCINATE or guess. BE HONEST about not knowing."
        elif intent == "general_info":
            context_section = "SYSTEM NOTE: No personal diary records found. This is a GENERAL KNOWLEDGE / MATH / FACTUAL question. IGNORE the lack of personal records and ANSWER the question using your own world knowledge. (e.g. If asked '2+2', say '4'. If asked about 'Vizag', tell them about Vizag)."

        # 4. Final Response Generation
        processed_system_prompt = MEMODIARY_PROMPT.format(
            user_name=user["name"] or "Friend",
            user_age=user["age"] or "Unknown",
            current_time=now,
            context_section=context_section
        )
        
        if not client:
            return "Environment configuration error. Please check your API key.", "😔"

        # Build contents for Gemini
        # gemini-1.5-flash-latest handles chat history automatically via contents list
        
        contents = []
        # Add recent history (last 5 messages)
        for msg in history[-5:]:
            role = msg.get("role")
            content = msg.get("content")
            if role and content and isinstance(content, str) and content.strip():
                # Map 'assistant' to 'model' for Gemini
                gemini_role = "model" if role == "assistant" else "user"
                contents.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)]))
            
        # Add current user input
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_input)]))

        try:
            # Added safety_settings to ensure common questions are not blocked
            # types is already imported globally
            safety_settings = [
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            ]

            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash", 
                config=types.GenerateContentConfig(
                    system_instruction=processed_system_prompt,
                    temperature=0.3, 
                    top_p=0.8,
                    safety_settings=safety_settings
                ),
                contents=contents
            )
            
            if not response.text:
                raise ValueError("EMPTY_RESPONSE")
            ai_text = response.text.strip()
        except Exception as api_err:
            with open("debug_errors.log", "a") as f:
                f.write(f"[{datetime.now()}] ERROR: {api_err}\n")
            safe_print(f"[{datetime.now()}] Gemini API Error: {api_err}")
            err_str = str(api_err).upper()
            if "429" in err_str:
                ai_text = "I'm holding too many thoughts right now. (ERR_429) 🤯"
            elif "503" in err_str:
                ai_text = "My thinking engine is briefly resting. (ERR_503) 😴"
            elif "SAFETY" in err_str or "BLOCKED" in err_str:
                ai_text = "I'm not comfortable reflecting on that. (ERR_BLOCKED) 🕊️"
            elif "EMPTY_RESPONSE" in err_str:
                ai_text = "I was lost in thought for a moment. (ERR_EMPTY) 😌"
            else:
                ai_text = f"I'm having a quiet moment. (ERR_API_FAILURE) 😌"
        
        # 5. Store AI response
        storage.add_entry(session_id, "model", ai_text)

        # 6. Simple mood extraction
        mood = "😌"
        if any(e in ai_text.lower() for e in ["😔", "😢", "sad", "sorry"]): mood = "😔"
        elif any(e in ai_text.lower() for e in ["😌", "calm", "peace"]): mood = "😌"
        elif any(e in ai_text.lower() for e in ["🤔", "wonder", "recall", "thinking"]): mood = "🤔"
        elif any(e in ai_text.lower() for e in ["🌟", "great", "happy", "joy", "wonderful"]): mood = "🌟"
        elif any(e in ai_text.lower() for e in ["😊", "good", "nice"]): mood = "😊"

        return ai_text, mood

    except Exception as e:
        safe_print(f"CRITICAL ERROR in get_ai_response: {e}")
        return "I'm having a quiet moment (Internal Connection Error). Let's try again in a bit. 😌", "⚠️"
