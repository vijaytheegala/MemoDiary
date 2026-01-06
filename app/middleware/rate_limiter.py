import time
from fastapi import Request, HTTPException
from typing import Dict, Tuple

class RateLimiter:
    def __init__(self, requests_per_minute: int = 20):
        self.requests_per_minute = requests_per_minute
        # Store as {key: (count, reset_time)}
        self.history: Dict[str, Tuple[int, float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        
        # Periodic cleanup (every 1000 calls or 10% chance)
        if hasattr(self, '_call_count'):
            self._call_count += 1
        else:
            self._call_count = 1
            
        if self._call_count % 100 == 0:
            self._cleanup(now)
            
        if key not in self.history:
            self.history[key] = (1, now + 60)
            return True

        count, reset_time = self.history[key]
        if now > reset_time:
            self.history[key] = (1, now + 60)
            return True

        if count < self.requests_per_minute:
            self.history[key] = (count + 1, reset_time)
            return True

        return False

    def _cleanup(self, now: float):
        """Remove expired entries from history to prevent memory leaks."""
        expired_keys = [k for k, v in self.history.items() if now > v[1]]
        for k in expired_keys:
            del self.history[k]

# Global instances for different purposes
chat_limiter = RateLimiter(requests_per_minute=15)
auth_limiter = RateLimiter(requests_per_minute=5)
tts_limiter = RateLimiter(requests_per_minute=20)
