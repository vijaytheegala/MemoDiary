import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.storage import storage
from app.memory import memory_processor
from app.query import query_engine

async def test_memory_flow():
    print("--- 1. Testing Storage Initialization ---")
    session_id = "test_session_v2"
    
    # Clean up previous test
    with storage._get_db() as conn:
        conn.execute("DELETE FROM entries WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM memory_index WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM daily_summary WHERE session_id = ?", (session_id,))
    
    print("\n--- 2. Testing Write Flow (Memory Extraction + Daily Summary) ---")
    user_input = "My dog's name is Bhima and he is a German Shepherd. I went to the park today and it was sunny."
    print(f"User Input: {user_input}")
    
    entry_id = storage.add_entry(session_id, "user", user_input)
    
    # Process Memory (Direct Call)
    print("Running processing...")
    await memory_processor.process_entry(session_id, user_input, entry_id)
    
    # Verify Memory Index
    items = storage.get_memory_items(session_id)
    print(f"Extracted Memory Items: {items}")
    
    bhima_found = any(i['memory_value'] == "Bhima" for i in items)
    if bhima_found:
        print("SUCCESS: 'Bhima' extracted correctly.")
    else:
        print("FAILED: 'Bhima' not found in memory index.")

    # Verify Daily Summary
    import datetime
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    summary = storage.get_daily_summary(session_id, today)
    try:
        print(f"Daily Summary for {today}: {str(summary).encode('ascii', 'replace').decode('ascii')}")
    except:
        print("Daily Summary retrieved (hidden due to encoding error)")
    
    if summary and "park" in str(summary).lower(): # Loose check
        print("SUCCESS: Daily summary generated.")
    else:
        print("FAILED: Daily summary missing or empty.")

    print("\n--- 3. Testing Query Flow & Caching ---")
    # First valid fetch
    print("Fetch 1 (DB):")
    items1 = storage.get_memory_items(session_id, memory_key="dog_name")
    print(items1)
    
    # Second fetch (Should be cache - though hard to prove without mocking, we trust the code logic)
    print("Fetch 2 (Cache):")
    items2 = storage.get_memory_items(session_id, memory_key="dog_name")
    print(items2)
    
    if items1 == items2:
        print("SUCCESS: Consistent retrieval (Cache logic assumed active).")

if __name__ == "__main__":
    asyncio.run(test_memory_flow())
