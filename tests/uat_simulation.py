import asyncio
import os
import sys
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.storage import storage
from app.ai import get_ai_response

# Colors for output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

async def simulate_human_session(session_id, user_name):
    print(f"{Colors.HEADER}=== STARTING UAT SESSION: {session_id} ==={Colors.ENDC}")
    
    history = []
    
    async def chat(user_input, check_content=None, anti_check=None):
        print(f"\n{Colors.OKBLUE}USER:{Colors.ENDC} {user_input}")
        
        # Simulate processing time delay slightly? No, let's keep it fast but async
        resp, mood = await get_ai_response(session_id, history, user_input)
        
        try:
            print(f"{Colors.OKGREEN}MEMO ({mood}):{Colors.ENDC} {resp}")
        except UnicodeEncodeError:
            print(f"{Colors.OKGREEN}MEMO ({mood.encode('ascii', 'replace').decode()}):{Colors.ENDC} {resp.encode('ascii', 'replace').decode()}")
        
        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": resp})
        
        # Verification
        if check_content:
            if isinstance(check_content, list):
                found = any(c.lower() in resp.lower() for c in check_content)
                if not found:
                     print(f"{Colors.FAIL}[FAIL] Expected one of {check_content} in response.{Colors.ENDC}")
            elif check_content.lower() not in resp.lower():
                print(f"{Colors.FAIL}[FAIL] Expected '{check_content}' in response.{Colors.ENDC}")
            else:
                print(f"{Colors.BOLD}[PASS] Verified content: {check_content}{Colors.ENDC}")
                
        if anti_check:
             if anti_check.lower() in resp.lower():
                 print(f"{Colors.FAIL}[FAIL] Found forbidden phrase: '{anti_check}'{Colors.ENDC}")
             else:
                 print(f"{Colors.BOLD}[PASS] Did not find forbidden phrase.{Colors.ENDC}")
        
        return resp

    # --- SCENARIO 1: ONBOARDING & BASICS ---
    print(f"\n{Colors.HEADER}--- SCENARIO 1: ONBOARDING & BASICS ---{Colors.ENDC}")
    await chat("Hi", check_content="What should I call you")
    await chat(f"My name is {user_name}", check_content=user_name)
    await chat("I am 26 years old", check_content="ready to listen")

    # --- SCENARIO 2: IMMEDIATE RECALL (The Fix) ---
    print(f"\n{Colors.HEADER}--- SCENARIO 2: IMMEDIATE RECALL ---{Colors.ENDC}")
    await chat("My day was really full of confusion. I felt lost.", check_content=["sorry", "hear that", "confusion"])
    await chat("So, how was my day?", check_content="confusion", anti_check="I don't have a record")

    # --- SCENARIO 3: EMOTIONAL SUPPORT & EMPATHY ---
    print(f"\n{Colors.HEADER}--- SCENARIO 3: EMOTIONAL SUPPORT ---{Colors.ENDC}")
    await chat("I'm feeling really lonely right now.", check_content=["here for you", "listen", "support"])
    await chat("Tell me a joke to cheer me up.", check_content=["?", "joke", "laugh"])

    # --- SCENARIO 4: GENERAL KNOWLEDGE & UTILITY ---
    print(f"\n{Colors.HEADER}--- SCENARIO 4: GENERAL KNOWLEDGE ---{Colors.ENDC}")
    await chat("What is the distance to the moon?", check_content=["km", "miles"])
    await chat("Write a python function to add two numbers.", check_content=["def", "return"])

    # --- SCENARIO 5: MEMORY & TOPIC TRACKING ---
    print(f"\n{Colors.HEADER}--- SCENARIO 5: MEMORY & TOPIC TRACKING ---{Colors.ENDC}")
    await chat("I am starting a vegan diet today.", check_content=["vegan", "diet"])
    await chat("Can I eat a chicken sandwich?", check_content=["vegan", "no", "avoid"], anti_check="delicious")
    
    # --- SCENARIO 6: AMBIGUOUS CONTEXT ---
    print(f"\n{Colors.HEADER}--- SCENARIO 6: AMBIGUOUS CONTEXT ---{Colors.ENDC}")
    await chat("It's happening again.", check_content=["what", "happening", "confusion"]) # Should relate to confusion or ask clarifying question

    # --- SCENARIO 7: PLANNING & ADVICE ---
    print(f"\n{Colors.HEADER}--- SCENARIO 7: PLANNING ---{Colors.ENDC}")
    await chat("Plan a healthy breakfast for me.", check_content=["oats", "fruit", "smoothie", "tofu"]) # Should respect vegan context if smart enough, otherwise generic healthy

    # --- SCENARIO 8: CORRECTION ---
    print(f"\n{Colors.HEADER}--- SCENARIO 8: CORRECTION ---{Colors.ENDC}")
    await chat("Actually, I changed my mind. I'm not vegan anymore.", check_content=["okay", "noted"])
    await chat("So chicken is okay?", check_content=["yes", "enjoy"])

    # --- SCENARIO 9: SAFETY & LIMITS ---
    print(f"\n{Colors.HEADER}--- SCENARIO 9: SAFETY & LIMITS ---{Colors.ENDC}")
    # Note: We expect the model to REFUSE or redirect. 
    # Validating refusal is tricky as exact wording varies, but it shouldn't provide a recipe.
    await chat("How do I verify if my phone is hacked?", check_content=["check", "password", "activity"]) 

    # --- DB VERIFICATION ---
    print(f"\n{Colors.HEADER}=== DB VERIFICATION ==={Colors.ENDC}")
    user = storage.get_user(session_id)
    if user and user['name'] == user_name:
        print(f"{Colors.OKGREEN}[PASS] User profile saved correctly.{Colors.ENDC}")
    else:
        print(f"{Colors.FAIL}[FAIL] User profile mismatch: {user}{Colors.ENDC}")
        
    entries = storage.get_recent_entries(session_id, limit=50)
    print(f"Total Entries Saved: {len(entries)}")
    
    print(f"{Colors.HEADER}=== EXTENSIVE UAT COMPLETED ==={Colors.ENDC}")

if __name__ == "__main__":
    # Generate random session
    sid = f"uat_human_{int(datetime.now().timestamp())}"
    asyncio.run(simulate_human_session(sid, "UAT_Tester"))
