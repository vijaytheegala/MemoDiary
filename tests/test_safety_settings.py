import os
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path

# Force load .env from the project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")

async def test_safety():
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})
    
    # Try using types enums
    try:
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE
            ),
        ]
        print("Testing with ENUMS...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents="Explain how AI works",
            config=types.GenerateContentConfig(safety_settings=safety_settings)
        )
        print("Success with ENUMS")
    except Exception as e:
        print(f"Failed with ENUMS: {e}")

    # Try using bare strings (to confirm failure)
    try:
        safety_settings_str = [
            types.SafetySetting(category="HATE_SPEECH", threshold="BLOCK_NONE"),
        ]
        print("\nTesting with STRINGS...")
        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents="Explain how AI works",
            config=types.GenerateContentConfig(safety_settings=safety_settings_str)
        )
        print("Success with STRINGS")
    except Exception as e:
        print(f"Failed with STRINGS: {e}")

if __name__ == "__main__":
    asyncio.run(test_safety())
