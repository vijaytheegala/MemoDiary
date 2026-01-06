
import asyncio
import edge_tts

async def check_methods():
    c = edge_tts.Communicate("test", "en-US-AriaNeural")
    print(dir(c))
    
if __name__ == "__main__":
    asyncio.run(check_methods())
