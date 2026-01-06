
import asyncio
import httpx
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"

async def test_endpoint(client, name, payload, expected_in_response=None, expected_min_length=0, not_expected_in_response=None):
    logger.info(f"--- Testing {name} ---")
    try:
        resp = await client.post(f"{BASE_URL}/api/chat", json=payload)
        resp_data = resp.json()
        response_text = resp_data.get('response', '')
        logger.info(f"Response: {response_text}")

        if expected_in_response and expected_in_response.lower() not in response_text.lower():
            logger.error(f"FAILED {name}: Expected '{expected_in_response}' not found.")
            return False
            
        if not_expected_in_response and not_expected_in_response.lower() in response_text.lower():
             logger.error(f"FAILED {name}: Found forbidden text '{not_expected_in_response}'.")
             return False

        if len(response_text) < expected_min_length:
            logger.error(f"FAILED {name}: Response too short.")
            return False

        logger.info(f"PASSED {name}")
        return True
    except Exception as e:
        logger.error(f"ERROR {name}: {e}")
        return False

async def verify_intelligence():
    async with httpx.AsyncClient(timeout=45.0) as client:
        # 1. Setup Session
        try:
            auth_resp = await client.post(f"{BASE_URL}/api/auth/anonymous")
            session_id = auth_resp.json().get("session_id")
            logger.info(f"Created Session: {session_id}")
        except Exception as e:
            logger.error(f"Auth Failed: {e}")
            return

        # 2. Test Arithmetic (General Info Fallback)
        # Should answer "4", NOT "I don't know"
        await test_endpoint(client, "Arithmetic (2+2)", 
            {"session_id": session_id, "message": "What is 2 + 2?"}, 
            expected_in_response="4")

        # 3. Test General Knowledge
        # Should answer about Vizag
        await test_endpoint(client, "General Knowledge (Vizag)", 
            {"session_id": session_id, "message": "What happened in Vizag yesterday?"}, 
            expected_min_length=20,
            not_expected_in_response="I don't have a record")

        # 4. Test Strict Privacy (Empty)
        # Should say "I don't handle" or "no record"
        await test_endpoint(client, "Strict Privacy (Empty)", 
            {"session_id": session_id, "message": "What did I eat yesterday?"}, 
            expected_in_response="record")

        # 5. Test Memory Storage & Retrieval
        # Inject memory
        await test_endpoint(client, "Inject Memory", 
            {"session_id": session_id, "message": "I met Kunal for coffee yesterday."})
        
        # Wait for background processing (schema extraction)
        logger.info("Waiting 5s for background memory extraction...")
        await asyncio.sleep(5)

        # Recall
        await test_endpoint(client, "Recall Memory", 
            {"session_id": session_id, "message": "Who did I meet yesterday?"}, 
            expected_in_response="Kunal")

if __name__ == "__main__":
    asyncio.run(verify_intelligence())
