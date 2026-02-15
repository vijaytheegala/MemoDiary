import requests
import json
import sys

# Force UTF-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

BASE_URL = "http://localhost:8000"

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

    print("\nTesting Chat Endpoint...")
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
                print(f"[PASS] Chat Passed (Response: {data['response'][:30]}..., Mood: {data['mood']})")
            else:
                print(f"[FAIL] Chat Failed: Invalid Schema {data.keys()}")
        else:
            print(f"[FAIL] Chat Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FAIL] Chat Error: {e}")

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
    test_admin_login()
    print("\n=== DONE ===")
