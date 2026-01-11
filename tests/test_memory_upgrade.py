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
    # Verify tables
    with storage._get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"Tables found: {tables}")
        if "memory_index" not in tables or "daily_summary" not in tables:
            print("FAILED: Missing new tables.")
            return

    session_id = "test_session_v1"
    
    # Clean up previous test
    with storage._get_db() as conn:
        conn.execute("DELETE FROM entries WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM memory_index WHERE session_id = ?", (session_id,))
    
    print("\n--- 2. Testing Write Flow (Memory Extraction) ---")
    user_input = "My dog's name is Bhima and he is a German Shepherd."
    print(f"User Input: {user_input}")
    
    entry_id = storage.add_entry(session_id, "user", user_input)
    
    # Process Memory (Direct Call)
    print("Running extraction...")
    await memory_processor.process_entry(session_id, user_input, entry_id)
    
    # Verify Memory Index
    items = storage.get_memory_items(session_id)
    print(f"Extracted Memory Items: {items}")
    
    bhima_found = any(i['memory_value'] == "Bhima" and i['memory_key'] == "dog_name" for i in items)
    if bhima_found:
        print("SUCCESS: 'Bhima' extracted correctly.")
    else:
        print("FAILED: 'Bhima' not found in memory index.")

    print("\n--- 3. Testing Query Flow (Routing & Retrieval) ---")
    question = "What is my dog's breed?"
    print(f"Question: {question}")
    
    current_time = "2026-01-09 12:00:00"
    analysis = await query_engine.analyze_query(question, current_time)
    print(f"Analysis Result: {analysis}")
    
    if analysis.get("intent") == "personal_fact" and "dog_breed" in analysis.get("memory_keys", []):
        print("SUCCESS: Intent and Key correctly identified.")
    else:
        print("WARNING: Analysis might have drifted. Checking retrieval anyway...")

    context = query_engine.retrieve_context(session_id, analysis)
    print(f"Retrieved Context:\n{context}")
    
    if "German Shepherd" in context:
        print("SUCCESS: Context contains the answer.")
    else:
        print("FAILED: Context missing answer.")

if __name__ == "__main__":
    asyncio.run(test_memory_flow())
