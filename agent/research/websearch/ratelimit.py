"""Search rate limit (ported from web-search-mcp src/rate-limiter.ts): at most N searches per minute and
5 at a time, so the engines aren't hammered when several requests are researched at once.
Difference: a search over the limit waits for the next minute instead of failing (research for two sources
runs more than 10 searches, and the original's error meant "no results" for the rest)."""
import threading
import time


class RateLimiter:
    def __init__(self, max_per_minute: int = 10, max_concurrent: int = 5):
        """At most ``max_per_minute`` calls a minute and ``max_concurrent`` at the same time."""
        self.max_per_minute = max_per_minute
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._lock = threading.Lock()
        self._count = 0
        self._window_start = time.monotonic()

    def execute(self, fn, *args, **kwargs):
        """Runs ``fn`` once the rate and concurrency limits allow it."""
        while True:
            with self._lock:
                now = time.monotonic()
                if now - self._window_start >= 60:
                    self._count, self._window_start = 0, now
                if self._count < self.max_per_minute:
                    self._count += 1
                    break
                wait = 60 - (now - self._window_start)
            time.sleep(max(wait, 0.1))
        with self._slots:
            return fn(*args, **kwargs)
