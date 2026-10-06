"""External intelligence providers. Provider failure => UNAVAILABLE, never MALICIOUS."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

from bot.verification.redaction import rex


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------
@dataclass
class NetworkVerdict:
    available: bool
    vpn: Optional[bool] = None
    proxy: Optional[bool] = None
    tor: Optional[bool] = None
    datacenter: Optional[bool] = None
    asn: Optional[str] = None
    reputation: Optional[float] = None      # 0.0 clean .. 1.0 abusive
    risk_score: Optional[float] = None      # 0.0 .. 1.0
    network_id: Optional[str] = None        # pseudonymous id for velocity / cluster
    provider: str = "unknown"


@dataclass
class RobloxProfile:
    available: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[str] = None        # ISO8601
    account_age_days: Optional[int] = None
    friend_count: Optional[int] = None
    description_length: Optional[int] = None
    has_verified_badge: Optional[bool] = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------
class NetworkProvider:
    name = "base"

    async def lookup(self, ip_or_token: Optional[str]) -> NetworkVerdict:
        return NetworkVerdict(available=False, provider=self.name)


class RobloxProvider:
    name = "base"

    async def lookup_user_by_id(self, user_id: int) -> RobloxProfile:
        return RobloxProfile(available=False, reason="provider not configured")

    async def lookup_user_by_username(self, username: str) -> RobloxProfile:
        return RobloxProfile(available=False, reason="provider not configured")


# ---------------------------------------------------------------------------
# Null implementations (default; honest UNAVAILABLE)
# ---------------------------------------------------------------------------
class NullNetworkProvider(NetworkProvider):
    name = "null"

    async def lookup(self, ip_or_token: Optional[str]) -> NetworkVerdict:
        return NetworkVerdict(available=False, provider=self.name)


class PublicRobloxProvider(RobloxProvider):
    """Uses Roblox's public, unauthenticated endpoints only.

    Endpoints used:
      - https://users.roblox.com/v1/users/{id}
      - https://friends.roblox.com/v1/users/{id}/friends/count
      - https://users.roblox.com/v1/usernames/users
    No credentials, no cookies, no auth.
    """
    name = "roblox_public"
    BASE_USERS = "https://users.roblox.com/v1"
    BASE_FRIENDS = "https://friends.roblox.com/v1"

    def __init__(self, timeout: float = 6.0, cache_ttl: float = 300.0) -> None:
        self._timeout = timeout
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, RobloxProfile]] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                    headers={"User-Agent": "DiscordSecurityBot/1.0 (verification)"},
                )
            return self._session

    async def close(self) -> None:
        async with self._lock:
            if self._session is not None and not self._session.closed:
                await self._session.close()

    def _from_cache(self, key: str) -> Optional[RobloxProfile]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, prof = entry
        if time.monotonic() - ts > self._cache_ttl:
            self._cache.pop(key, None)
            return None
        return prof

    def _to_cache(self, key: str, prof: RobloxProfile) -> None:
        self._cache[key] = (time.monotonic(), prof)

    async def lookup_user_by_id(self, user_id: int) -> RobloxProfile:
        key = f"id:{user_id}"
        cached = self._from_cache(key)
        if cached:
            return cached

        try:
            session = await self._get_session()
            async with session.get(f"{self.BASE_USERS}/users/{user_id}") as resp:
                if resp.status == 404:
                    prof = RobloxProfile(available=True, user_id=user_id, reason="not_found")
                    self._to_cache(key, prof)
                    return prof
                if resp.status != 200:
                    return RobloxProfile(available=False, reason=f"http_{resp.status}")
                data = await resp.json()

            created = data.get("created")
            age_days = _iso_age_days(created) if created else None

            friend_count = None
            try:
                async with session.get(f"{self.BASE_FRIENDS}/users/{user_id}/friends/count") as fresp:
                    if fresp.status == 200:
                        fdata = await fresp.json()
                        friend_count = int(fdata.get("count", 0))
            except Exception:
                friend_count = None

            prof = RobloxProfile(
                available=True,
                user_id=int(data.get("id", user_id)),
                username=str(data.get("name", ""))[:64],
                display_name=str(data.get("displayName", ""))[:64],
                created_at=str(created) if created else None,
                account_age_days=age_days,
                friend_count=friend_count,
                description_length=len(str(data.get("description", "") or "")),
                has_verified_badge=bool(data.get("hasVerifiedBadge", False)),
                reason="ok",
            )
            self._to_cache(key, prof)
            return prof
        except Exception as exc:
            return RobloxProfile(available=False, reason="error:" + rex(exc)[:80])

    async def lookup_user_by_username(self, username: str) -> RobloxProfile:
        key = f"un:{username.lower()}"
        cached = self._from_cache(key)
        if cached:
            return cached
        try:
            session = await self._get_session()
            payload = {"usernames": [username], "excludeBannedUsers": False}
            async with session.post(f"{self.BASE_USERS}/usernames/users", json=payload) as resp:
                if resp.status != 200:
                    return RobloxProfile(available=False, reason=f"http_{resp.status}")
                data = await resp.json()
            entries = data.get("data") or []
            if not entries:
                prof = RobloxProfile(available=True, reason="not_found")
                self._to_cache(key, prof)
                return prof
            uid = int(entries[0].get("id"))
            prof = await self.lookup_user_by_id(uid)
            self._to_cache(key, prof)
            return prof
        except Exception as exc:
            return RobloxProfile(available=False, reason="error:" + rex(exc)[:80])


def _iso_age_days(iso: str) -> Optional[int]:
    try:
        from datetime import datetime, timezone
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((datetime.now(timezone.utc) - dt).days, 0)
    except Exception:
        return None
