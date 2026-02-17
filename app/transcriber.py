import os
from google import genai
from google.genai import types
from app.utils.ai_utils import generate_with_retry
from app.key_manager import key_manager
from dotenv import load_dotenv
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Transcriber:
    def __init__(self):
        pass

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """
        Transcribes audio bytes using Gemini 2.0 Flash.
        """
        # Client generation is handled by generate_with_retry if needed, 
        # or we could pass one. optimize later if needed.

        try:
            prompt = "Transcribe the following audio exactly. Return ONLY the spoken text. Do not add any commentary."
            
            # Using shared retry logic
            response = await generate_with_retry(
                model_name="gemini-2.0-flash", 
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
