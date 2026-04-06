import os
from google import genai
from google.genai import types
from app.key_manager import key_manager
from dotenv import load_dotenv
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Transcriber:
    def __init__(self):
        pass

    def _get_client(self):
        key = key_manager.get_next_key()
        if key:
            return genai.Client(api_key=key, http_options={'api_version': 'v1beta'})
        return None

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """
        Transcribes audio bytes using Gemini 2.0 Flash.
        """
        client = self._get_client()
        if not client:
            raise ValueError("No API Key available")

        try:
            prompt = "Transcribe the following audio exactly. Return ONLY the spoken text. Do not add any commentary."
            
            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash", 
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt),
                            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
                        ]
                    )
                ]
            )
            
            return response.text.strip()
            
        except Exception as e:
            print(f"Transcription Error: {e}")
            raise e

# Global instance
transcriber = Transcriber()
