import os
import random
from typing import List
from dotenv import load_dotenv
from pathlib import Path

# Force load .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class KeyManager:
    """
    Manages a pool of API keys and rotates them to distribute load.
    """
    def __init__(self):
        self.keys: List[str] = []
        self._load_keys()
        
    def _load_keys(self):
        # Load primary key
        k1 = os.getenv("GEMINI_API_KEY")
        if k1: self.keys.append(k1)
        
        # Load secondary keys (pattern: GEMINI_API_KEY_2, _3, etc.)
        i = 2
        while True:
            k = os.getenv(f"GEMINI_API_KEY_{i}")
            if k:
                self.keys.append(k)
                i += 1
            else:
                break
                
        # Shuffle specifically to avoid hitting the same key first on every restart
        random.shuffle(self.keys)
        
    def get_next_key(self) -> str:
        """Returns a key from the pool (Round Robin or Random)."""
        if not self.keys:
            return None
        # Simple random selection for now - statistically balances load
        return random.choice(self.keys)

    def get_key_count(self) -> int:
        return len(self.keys)

# Global Instance
key_manager = KeyManager()
