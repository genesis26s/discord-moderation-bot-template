"""Async sliding-window rate limiter with per-key buckets."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque


class RateLimitExceeded(Exception):
    def __init__(self, key: str, retry_after: float):
        super().__init__(f"Rate limit exceeded for {key}")
        self.key = key
        self.retry_after = retry_after


class RateLimiter:
    """Sliding-window limiter. Thread-safe via a single asyncio lock."""

    def __init__(self) -> None:
        self._windows: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_seconds: float) -> None:
        """Record one hit; raise RateLimitExceeded if the limit is already reached."""
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._windows[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = window_seconds - (now - bucket[0])
                raise RateLimitExceeded(key, max(retry_after, 0.1))
            bucket.append(now)

    async def check(self, key: str, limit: int, window_seconds: float) -> bool:
        """Non-raising variant. Returns True if within limit."""
        try:
            await self.hit(key, limit, window_seconds)
            return True
        except RateLimitExceeded:
            return False

    async def count(self, key: str, window_seconds: float) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._windows[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            return len(bucket)
