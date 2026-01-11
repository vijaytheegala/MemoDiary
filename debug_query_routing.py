
import asyncio
from app.query import QueryEngine, QUERY_ANALYSIS_PROMPT
from datetime import datetime

# Mock the storage to avoid needing real DB for this routing test, 
# or just let it run and see the "print" outputs if we didn't mock.
# Actually, we want to see the Analysis Output.

async def test_routing():
    engine = QueryEngine()
    
    # The queries that failed
    queries = [
        "So, can you tell me what is my favorite color and favorite bike and favorite car and favorite movie?",
        "do you remember anything what I have spoken uh before like in a while before a few minutes ago about my project"
    ]
    
    current_time = datetime.now().isoformat()
    
    print("--- DEBUGGING QUERY ROUTING ---")
    
    for q in queries:
        print(f"\nINPUT: {q}")
        try:
            # We are calling the internal logic that calls the LLM
            analysis = await engine.analyze_query(q, current_time)
            print("ANALYSIS OUTPUT:")
            print(analysis)
            
            intent = analysis.get("intent")
            keys = analysis.get("memory_keys", [])
            print(f"-> INTENT: {intent}")
            print(f"-> KEYS: {keys}")
            
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_routing())
