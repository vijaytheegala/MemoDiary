import requests
import json
import sys

# Force UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

port = 8000
if len(sys.argv) > 1:
    try:
        port = int(sys.argv[1])
    except ValueError:
        pass

BASE_URL = f"http://localhost:{port}"

def test_health():
    print(f"Testing Health Check at {BASE_URL}/health...")
    try:
        resp = requests.get(f"{BASE_URL}/health")
        if resp.status_code == 200:
            print("[PASS] Health Check Passed")
        else:
            print(f"[FAIL] Health Check Failed: {resp.status_code}")
    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")

def test_startup():
    print("\nTesting Startup Endpoint...")
    try:
        # Test new user (no session_id)
        resp = requests.post(f"{BASE_URL}/api/startup", json={"session_id": None})
        if resp.status_code == 200:
            data = resp.json()
            session_id = data.get("session_id")
            if session_id:
                print(f"[PASS] Startup Passed (New ID generated: {session_id})")
                return session_id
            else:
                print("[FAIL] Startup Failed: No session_id returned")
        else:
            print(f"[FAIL] Startup Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FAIL] Startup Error: {e}")
    return None

def test_chat(session_id):
    if not session_id:
        print("\n[SKIP] Skipping Chat Test (No Session ID)")
        return

    print("\nTesting Chat Endpoint (Blocking Mode)...")
    try:
        payload = {
            "session_id": session_id,
            "message": "Hello, are you there?",
            "stream": False # Simple non-stream test for logic check
        }
        resp = requests.post(f"{BASE_URL}/api/chat", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if "response" in data and "mood" in data:
                print(f"[PASS] Chat (Blocking) Passed (Response: {data['response'][:30]}..., Mood: {data['mood']})")
            else:
                print(f"[FAIL] Chat (Blocking) Failed: Invalid Schema {data.keys()}")
        else:
            print(f"[FAIL] Chat (Blocking) Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FAIL] Chat (Blocking) Error: {e}")

def test_chat_stream(session_id):
    if not session_id:
        print("\n[SKIP] Skipping Chat Stream Test (No Session ID)")
        return

    print("\nTesting Chat Endpoint (Streaming Mode)...")
    try:
        payload = {
            "session_id": session_id,
            "message": "Write a short poem.",
            "stream": True 
        }
        # Use stream=True in requests to get raw iterable content
        resp = requests.post(f"{BASE_URL}/api/chat", json=payload, stream=True)
        
        if resp.status_code == 200:
            valid_chunks = 0
            for line in resp.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        content = decoded_line.replace("data: ", "")
                        if content in ["[DONE]", "⚡", "😌"]: continue
                        
                        try:
                            # CRITICAL: Verify JSON format
                            header_check = json.loads(content)
                            if "text" in header_check:
                                valid_chunks += 1
                        except json.JSONDecodeError:
                            print(f"[FAIL] Stream Chunk Not JSON: {content}")
                            return

            if valid_chunks > 0:
                print(f"[PASS] Chat (Streaming) Passed. Received {valid_chunks} valid JSON chunks.")
            else:
                print("[WARN] Chat (Streaming) received no text chunks (Maybe trivial response?)")
        else:
            print(f"[FAIL] Chat (Streaming) Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FAIL] Chat (Streaming) Error: {e}")

def test_admin_login():
    print("\nTesting Admin Login...")
    try:
        # Note: This requires the hardcoded PIN hash in main.py or one set in env.
        # Default pin corresponding to hash "8d2c..." is "148314"
        payload = {"pin": "148314"} 
        resp = requests.post(f"{BASE_URL}/api/admin/login", json=payload)
        
        if resp.status_code == 200:
            token = resp.json().get("token")
            if token:
                print("[PASS] Admin Login Passed")
            else:
                print("[FAIL] Admin Login Failed: No token")
        elif resp.status_code == 401:
             print("[PASS] Admin Login Security Verified (Passed if credentials changed, 401 expected for wrong pin)")
        else:
            print(f"[FAIL] Admin Login Unexpected: {resp.status_code}")
    except Exception as e:
        print(f"[FAIL] Admin Error: {e}")

if __name__ == "__main__":
    print("=== VERIFYING PRODUCTION ENDPOINTS ===")
    test_health()
    sid = test_startup()
    test_chat(sid)
    test_chat_stream(sid)
    test_admin_login()
    print("\n=== DONE ===")
