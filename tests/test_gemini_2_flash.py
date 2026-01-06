import os
import asyncio
from google import genai
from dotenv import load_dotenv
from pathlib import Path

# Force load .env from the project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("CRITICAL: GEMINI_API_KEY not found in .env")
    exit(1)

try:
    # User's curl command used v1beta
    client = genai.Client(
        api_key=api_key,
        http_options={'api_version': 'v1beta'}
    )

    print("Testing gemini-2.0-flash...")
    # Using the exact model name from user's curl
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Explain how AI works in a few words",
    )

    print("Response received:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
