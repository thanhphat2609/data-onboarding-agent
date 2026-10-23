"""Search rate limit (ported from web-search-mcp src/rate-limiter.ts): at most N searches per minute and
5 at a time, so the engines aren't hammered when several requests are researched at once."""
import threading
import time


class RateLimitExceeded(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, max_per_minute: int = 10, max_concurrent: int = 5):
        self.max_per_minute = max_per_minute
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._lock = threading.Lock()
        self._count = 0
        self._window_start = time.monotonic()

    def execute(self, fn, *args, **kwargs):
        with self._lock:
            now = time.monotonic()
            if now - self._window_start >= 60:
                self._count, self._window_start = 0, now
            if self._count >= self.max_per_minute:
                wait = int(60 - (now - self._window_start)) + 1
                raise RateLimitExceeded(f"Rate limit exceeded. Please wait {wait} seconds.")
            self._count += 1
        with self._slots:
            return fn(*args, **kwargs)
