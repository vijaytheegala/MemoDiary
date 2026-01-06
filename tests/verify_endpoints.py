import requests
import sys

BASE_URL = "http://localhost:8000"

def test_health():
    print("Testing /health...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200 and response.json() == {"status": "healthy"}:
            print("[PASS] /health passed")
        else:
            print(f"[FAIL] /health failed: {response.status_code} {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] /health failed with exception: {e}")
        sys.exit(1)

def test_auth_anonymous():
    print("Testing /api/auth/anonymous...")
    try:
        response = requests.post(f"{BASE_URL}/api/auth/anonymous")
        if response.status_code == 200:
            data = response.json()
            if "session_id" in data and data["status"] == "ready":
                print(f"[PASS] /api/auth/anonymous passed (Session ID: {data['session_id']})")
            else:
                print(f"[FAIL] /api/auth/anonymous failed validation: {data}")
                sys.exit(1)
        else:
            print(f"[FAIL] /api/auth/anonymous failed: {response.status_code} {response.text}")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] /api/auth/anonymous failed with exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_health()
    test_auth_anonymous()
