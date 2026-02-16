from fastapi.testclient import TestClient
import json
import sys
import os

# Mock imports before app load
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock key_manager to prevent real API calls during startup checks
from unittest.mock import MagicMock
sys.modules['app.key_manager'] = MagicMock()
sys.modules['app.storage'] = MagicMock()
sys.modules['app.ai'] = MagicMock()

from app.main import app
from app.ai import get_ai_response

client = TestClient(app)

async def mock_ai_generator(*args, **kwargs):
    # Simulate AI returning chunks with newlines
    yield "Hello.\n"
    yield "This is a test.\n"
    yield "Hope it works!"

async def mock_get_ai_response(*args, **kwargs):
    return mock_ai_generator()

def test_sse_endpoint_structure():
    print("--- Testing /api/chat SSE JSON Format ---")
    
    # Setup Mock
    # We must use side_effect because get_ai_response is called as a function
    # that returns a coroutine.
    get_ai_response.side_effect = mock_get_ai_response
    
    # Make Request
    response = client.post("/api/chat", json={
        "session_id": "test_session",
        "message": "test",
        "stream": True
    })
    
    assert response.status_code == 200
    
    # Analyze Output
    content = response.text
    blocks = content.split('\n\n')
    
    valid_json_count = 0
    
    for block in blocks:
        if not block.strip(): continue
        print(f"DEBUG BLOCK: {repr(block)}")
        
        lines = block.split('\n')
        for line in lines:
            if line.startswith("data: "):
                payload = line.replace("data: ", "")
                if payload == "[DONE]": continue
                if payload == "⚡": continue # Mood
                if payload == "😌": continue # Mood
                
                try:
                    data = json.loads(payload)
                    print(f"  -> Valid JSON detected: {data}")
                    if "text" in data:
                        valid_json_count += 1
                except json.JSONDecodeError:
                    print(f"  -> [FAIL] Invalid JSON: {payload}")
                    assert False, f"Payload is not valid JSON: {payload}"

    print(f"Total Valid Text JSON Chunks: {valid_json_count}")
    if valid_json_count >= 3:
        print("[PASS] Endpoint is streaming valid JSON")
    else:
        print("[FAIL] Not enough JSON chunks (Mock setup issue?)")
        assert False

if __name__ == "__main__":
    try:
        test_sse_endpoint_structure()
        print("\n=== INTEGRATION TEST PASSED ===")
    except AssertionError as e:
        print(f"\n=== INTEGRATION TEST FAILED: {e} ===")
        sys.exit(1)
    except Exception as e:
        print(f"\n=== INTEGRATION TEST ERROR: {e} ===")
        sys.exit(1)
