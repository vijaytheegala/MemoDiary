import edge_tts
import asyncio
import os

class TTSEngine:
    def __init__(self, voice="en-US-AriaNeural"):
        """
        Initializes the TTS Engine.
        Default voice is 'en-US-AriaNeural' which is a sweet, friendly female voice.
        Other good options: 'en-US-JennyNeural' (warm, friendly).
        """
        self.voice = voice

    async def generate_speech_stream(self, text: str) -> None:
        """
        Generates a stream of audio bytes from the given text.
        """
        communicate = edge_tts.Communicate(text, self.voice, rate="+0%", pitch="+0Hz")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def generate_speech_file(self, text: str, output_path: str):
        """
        Generates an MP3 file from the given text.
        """
        communicate = edge_tts.Communicate(text, self.voice, rate="+0%", pitch="+0Hz")
        await communicate.save(output_path)

# Initialize a global TTS engine
# Aria is very balanced: friendly, sweet, and professional.
tts_engine = TTSEngine(voice="en-US-AriaNeural")
