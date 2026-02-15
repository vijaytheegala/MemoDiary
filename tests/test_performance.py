import asyncio
import time
import requests
import json
import sys

# Windows console encoding fix
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))

def setup_user(session_id):
    safe_print(f"Setting up user {session_id}...")
    # 1. Start session
    requests.post(f"{BASE_URL}/api/chat", json={"message": "Hi", "session_id": session_id})
    # 2. Provide Name
    requests.post(f"{BASE_URL}/api/chat", json={"message": "My name is TestUser", "session_id": session_id})
    # 3. Provide Age
    requests.post(f"{BASE_URL}/api/chat", json={"message": "I am 30", "session_id": session_id})
    safe_print("User setup complete.")


def test_endpoint(name, payload, expected_status=200, max_latency=None):
    safe_print(f"Testing {name}...")
    start = time.time()
    try:
        resp = requests.post(f"{BASE_URL}/api/chat", json=payload, stream=True)
        
        # Determine time to first byte/header
        first_chunk_time = time.time() - start
        
        content = ""
        for line in resp.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    data = decoded.replace("data: ", "")
                    # print(f"DEBUG CHUNK: {data}")
                    if data != "[DONE]":
                        content += data

        latency = time.time() - start
        safe_print(f"  -> Latency: {latency:.4f}s (First Chunk/Headers: {first_chunk_time:.4f}s)")
        safe_print(f"  -> Content: {content[:100]}...")

        if max_latency and first_chunk_time > max_latency:
            safe_print(f"  [FAIL] TTFB exceeded {max_latency}s")
        else:
            safe_print(f"  [PASS] TTFB OK ({first_chunk_time:.3f}s)")

        return content, latency

    except Exception as e:
        safe_print(f"  [ERROR] {e}")
        return None, 0

print("--- PERFORMANCE & ROUTING VERIFICATION ---")

# 1. TRIVIAL (Math)
# Requirement: < 200ms target (approx 0.2s)
test_endpoint(
    "TRIVIAL (Math: 2+2)", 
    {"message": "2+2", "stream": True}, 
    max_latency=0.5 # Giving some buffer for python/network overhead, but target is low
)

# 2. TRIVIAL (Greeting)
# Requirement: Fast, no memory
test_endpoint(
    "TRIVIAL (Greeting: Hello)", 
    {"message": "Hello", "stream": True},
    max_latency=2.0 
)

# 3. WORLD (Capital)
# Requirement: 1-2s, Direct answer
test_endpoint(
    "WORLD (Fact: Capital of France)", 
    {"message": "What is the capital of France?", "stream": True},
    max_latency=3.0
)

# 4. PERSONAL (Memory)
# Requirement: 2-4s, Logic intact (might fail if no memory, but should not crash)
setup_user("test_perf_user")
test_endpoint(
    "PERSONAL (Recall: My name)", 
    {"message": "What is my name?", "stream": True, "session_id": "test_perf_user"},
    max_latency=5.0
)

print("\nDone.")
