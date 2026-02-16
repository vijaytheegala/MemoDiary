import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.storage import storage
from app.ai import get_ai_response

async def reproduce_issue():
    print("--- Starting Reproduction Test ---")
    
    # 1. Create a fresh session
    session_id = f"test_user_{int(datetime.now().timestamp())}"
    print(f"Session ID: {session_id}")
    
    storage.create_user(session_id)
    storage.update_user_profile(session_id, name="Tester", age="30", onboarding_complete=True)
    
    # 2. User states a fact about their day
    user_input_1 = "My day was full of confusion."
    print(f"\nUser: {user_input_1}")
    
    # We cheat and bypass full pipeline for setup, just adding entry to DB
    # But wait, we need the AI to process it so memory might form if it was working
    # Let's run full AI response for the first input too
    
    resp1, mood1 = await get_ai_response(session_id, [], user_input_1)
    print(f"AI: {resp1}")
    
    # 3. User asks about their day immediately
    user_input_2 = "How was my day today?"
    print(f"\nUser: {user_input_2}")
    
    # Get history for context
    history = [
        {"role": "user", "content": user_input_1},
        {"role": "assistant", "content": resp1}
    ]
    
    resp2, mood2 = await get_ai_response(session_id, history, user_input_2)
    print(f"AI: {resp2}")
    
    # 4. Verification
    failure_phrase = "I don't have a record of that"
    success_keyword = "confusion"
    
    if failure_phrase in resp2:
        print("\n[FAIL] Reproduction Successful: AI forgot the day's event.")
    elif success_keyword in resp2.lower():
        print("\n[PASS] AI remembered the confusion.")
    else:
        print("\n[WARN] AI gave a generic response without specific recall.")

if __name__ == "__main__":
    asyncio.run(reproduce_issue())
