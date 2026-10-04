"""Tracks join velocity for anti-raid."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque


class RaidService:
    def __init__(self) -> None:
        self._joins: dict[int, Deque[float]] = defaultdict(lambda: deque(maxlen=200))

    def record_join(self, guild_id: int) -> int:
        now = time.monotonic()
        q = self._joins[guild_id]
        q.append(now)
        return len(q)

    def joins_in_window(self, guild_id: int, window_seconds: int) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        q = self._joins[guild_id]
        while q and q[0] < cutoff:
            q.popleft()
        return len(q)

    def clear(self, guild_id: int) -> None:
        self._joins.pop(guild_id, None)
