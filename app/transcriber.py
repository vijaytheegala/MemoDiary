import os
from groq import AsyncGroq
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
            return AsyncGroq(api_key=key)
        return None

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """
        Transcribes audio bytes using Groq Whisper.
        """
        client = self._get_client()
        if not client:
            raise ValueError("No API Key available")

        try:
            # Note: Groq expects a tuple (filename, bytes) for the file.
            response = await client.audio.transcriptions.create(
                file=("audio.webm", audio_bytes),
                model="whisper-large-v3",
                prompt="Transcribe the following audio exactly. Return ONLY the spoken text. Do not add any commentary.",
                response_format="text"
            )
            
            return response.strip()
            
        except Exception as e:
            print(f"Transcription Error: {e}")
            raise e

# Global instance
transcriber = Transcriber()
