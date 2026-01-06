import asyncio
import httpx
import sys
import os

BASE_URL = "http://127.0.0.1:8000"

async def verify_system():
    print("--- Starting Final System Verification ---")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Check Health
        try:
            resp = await client.get(f"{BASE_URL}/health")
            print(f"[Health] Status: {resp.status_code}, Body: {resp.json()}")
        except Exception as e:
            print(f"[Health] FAILED: {e}")

        # 2. Check Auth
        session_id = None
        try:
            resp = await client.post(f"{BASE_URL}/api/auth/anonymous")
            data = resp.json()
            session_id = data.get("session_id")
            print(f"[Auth] Generated Session: {session_id}")
        except Exception as e:
            print(f"[Auth] FAILED: {e}")

        if not session_id:
            print("Aborting remaining tests due to Auth failure.")
            return

        # 3. Check Factual Query (2+2)
        try:
            print("[Chat] Testing factual query: 'What is 2 + 2?'")
            resp = await client.post(f"{BASE_URL}/api/chat", json={
                "session_id": session_id,
                "message": "What is 2 + 2?"
            })
            data = resp.json()
            print(f"[Chat] Response: {data.get('response')}")
            if "4" in str(data.get("response")):
                print("[Chat] Factual Query PASSED")
            else:
                print("[Chat] Factual Query logic might be unstable.")
        except Exception as e:
            print(f"[Chat] Factual Query FAILED: {e}")

        # 4. Check Onboarding & Memory
        try:
            print("[Memory] Setting name to 'Alex'...")
            await client.post(f"{BASE_URL}/api/chat", json={
                "session_id": session_id,
                "message": "Alex"
            })
            print("[Memory] Recalling name...")
            resp = await client.post(f"{BASE_URL}/api/chat", json={
                "session_id": session_id,
                "message": "What is my name?"
            })
            data = resp.json()
            print(f"[Memory] Response: {data.get('response')}")
            if "Alex" in str(data.get("response")):
                print("[Memory] Recalled name correctly. PASSED")
            else:
                print("[Memory] Recall FAILED")
        except Exception as e:
            print(f"[Memory] Flow FAILED: {e}")

        # 5. Check General Info Fallback (Hybrid)
        try:
            print("[Fallback] Testing: 'What happened in London?'")
            resp = await client.post(f"{BASE_URL}/api/chat", json={
                "session_id": session_id,
                "message": "What happened in London?"
            })
            data = resp.json()
            response_text = data.get('response', '')
            print(f"[Fallback] Response: {response_text[:100]}...")
            
            # Should have NO personal record disclaimer BUT still answer generally
            if "don't have a record" in response_text and len(response_text) > 50:
                 print("[Fallback] Hybrid Response Logic PASSED")
            else:
                 print(f"[Fallback] Logic Check: Expected hybrid response. Got: {response_text}")

        except Exception as e:
            print(f"[Fallback] FAILED: {e}")

        # 6. Check Strict Personal Fallback
        try:
             print("[Privacy] Testing: 'What did I eat yesterday?' (Should fail recall)")
             resp = await client.post(f"{BASE_URL}/api/chat", json={
                "session_id": session_id,
                "message": "What did I eat yesterday?"
            })
             data = resp.json()
             if "don't have a record" in data.get('response'):
                 print("[Privacy] Strict Fallback PASSED")
             else:
                 print(f"[Privacy] Failed strict fallback. Got: {data.get('response')}")
        except Exception as e:
            print(f"[Privacy] FAILED: {e}")

    print("--- Verification Complete ---")

if __name__ == "__main__":
    # Ensure server is running or this will fail
    asyncio.run(verify_system())
