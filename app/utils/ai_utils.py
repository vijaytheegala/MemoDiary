import asyncio
import logging
from google import genai
from google.genai import types
from app.key_manager import key_manager

# Configure logging
logger = logging.getLogger(__name__)

MAX_RETRIES = 3

def get_client():
    """Get a client with a rotated key."""
    key = key_manager.get_next_key()
    if key:
        return genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
    return None

async def generate_with_retry(model_name: str, contents: any, config: types.GenerateContentConfig = None, client=None) -> any:
    """
    Wraps generate_content with retry logic for 429 (Rate Limit) and 503 (Service Unavailable) errors.
    Expands backoff: 2s, 4s, 8s...
    Rotates key on 429.
    """
    delay = 2 # Start with 2s delay
    
    # Use provided client or get a new one
    current_client = client if client else get_client()

    for attempt in range(MAX_RETRIES + 1):
        try:
            if not current_client:
                current_client = get_client()
                if not current_client:
                     logger.error("No Gemini Client Available (Keys missing?)")
                     raise ValueError("No Client Available")

            return await current_client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
        except Exception as e:
            err_str = str(e)
            # Check for Rate Limit (429) or Service Unavailable (503) which is also transient
            if "429" in err_str or "503" in err_str:
                if attempt < MAX_RETRIES:
                    logger.warning(f"[AI RETRY] Error {err_str} - Retrying in {delay}s... (Attempt {attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    delay *= 2
                    
                    # Rotate Key for next attempt if it was a 429/503
                    # This helps distribute load across keys
                    new_client = get_client()
                    if new_client:
                        current_client = new_client
                    continue
            
            # If we are here, it's either not a retryable error OR we ran out of retries
            logger.error(f"[AI FAILURE] Exhausted retries or non-retryable error: {e}")
            raise e

async def generate_with_retry_stream(model_name: str, contents: any, config: types.GenerateContentConfig = None, client=None) -> any:
    """
    Wraps generate_content_stream with retry logic for 429/503 errors.
    Returns an async generator.
    """
    delay = 2
    current_client = client if client else get_client()

    for attempt in range(MAX_RETRIES + 1):
        try:
            if not current_client:
                current_client = get_client()
                if not current_client:
                     logger.error("No Gemini Client Available (Keys missing?)")
                     raise ValueError("No Client Available")

            return await current_client.aio.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config
            )
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "503" in err_str:
                if attempt < MAX_RETRIES:
                    logger.warning(f"[AI STREAM RETRY] Error {err_str} - Retrying in {delay}s... (Attempt {attempt+1}/{MAX_RETRIES})")
                    await asyncio.sleep(delay)
                    delay *= 2
                    
                    new_client = get_client()
                    if new_client:
                        current_client = new_client
                    continue
            
            logger.error(f"[AI STREAM FAILURE] Exhausted retries: {e}")
            raise e
