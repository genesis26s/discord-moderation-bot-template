"""Verification sessions with strict state machine."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class VState(str, Enum):
    CREATED = "CREATED"
    SECURITY_CHECK = "SECURITY_CHECK"
    LAYER_SELECTED = "LAYER_SELECTED"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    CHALLENGE_ACTIVE = "CHALLENGE_ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"


_TRANSITIONS: dict = {
    VState.CREATED: {VState.SECURITY_CHECK, VState.EXPIRED, VState.FAILED},
    VState.SECURITY_CHECK: {VState.LAYER_SELECTED, VState.MANUAL_REVIEW, VState.EXPIRED, VState.FAILED},
    VState.LAYER_SELECTED: {VState.CHALLENGE_REQUIRED, VState.QUARANTINED, VState.MANUAL_REVIEW, VState.EXPIRED},
    VState.CHALLENGE_REQUIRED: {VState.CHALLENGE_ACTIVE, VState.EXPIRED, VState.FAILED},
    VState.CHALLENGE_ACTIVE: {VState.COMPLETED, VState.FAILED, VState.EXPIRED, VState.MANUAL_REVIEW},
    VState.COMPLETED: set(),
    VState.FAILED: {VState.CREATED},
    VState.EXPIRED: {VState.CREATED},
    VState.QUARANTINED: {VState.MANUAL_REVIEW, VState.COMPLETED, VState.REJECTED},
    VState.MANUAL_REVIEW: {VState.COMPLETED, VState.REJECTED, VState.QUARANTINED},
    VState.REJECTED: set(),
}


class InvalidTransition(Exception):
    pass


@dataclass
class VerificationSession:
    session_id: str
    guild_id: int
    user_id: int
    state: VState = VState.CREATED
    created_at: float = field(default_factory=time.monotonic)
    expires_at: float = 0.0
    challenge_token: str = ""
    challenge_attempts: int = 0
    risk_score: int = 0
    risk_level: str = "LOW"
    confidence: float = 0.0
    layer: int = 1
    assessment_id: Optional[int] = None
    last_transition_at: float = field(default_factory=time.monotonic)
    notes: list = field(default_factory=list)

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.monotonic() > self.expires_at

    def can_transition(self, target: VState) -> bool:
        return target in _TRANSITIONS.get(self.state, set())

    def transition(self, target: VState) -> None:
        if not self.can_transition(target):
            raise InvalidTransition("Cannot move from " + self.state.value + " to " + target.value)
        self.state = target
        self.last_transition_at = time.monotonic()

    def to_row(self) -> tuple:
        return (
            self.session_id, self.guild_id, self.user_id, self.state.value,
            int(time.time()), int(self.expires_at), self.risk_score,
            self.risk_level, self.confidence, self.layer,
            self.assessment_id or 0, self.challenge_attempts,
        )


class SessionManager:
    def __init__(self, timeout_seconds: int = 900) -> None:
        self._sessions: dict = {}
        self._by_user: dict = {}
        self._lock = asyncio.Lock()
        self.timeout_seconds = timeout_seconds

    def _new_id(self) -> str:
        return "vs_" + secrets.token_urlsafe(16)

    def _new_challenge(self) -> str:
        return secrets.token_urlsafe(24)

    async def create(self, guild_id: int, user_id: int) -> VerificationSession:
        async with self._lock:
            existing_key = (guild_id, user_id)
            existing_id = self._by_user.get(existing_key)
            if existing_id:
                sess = self._sessions.get(existing_id)
                if sess and sess.state in (VState.CREATED, VState.SECURITY_CHECK, VState.LAYER_SELECTED,
                                           VState.CHALLENGE_REQUIRED, VState.CHALLENGE_ACTIVE):
                    return sess
                if sess:
                    self._sessions.pop(existing_id, None)
                    self._by_user.pop(existing_key, None)

            sess = VerificationSession(
                session_id=self._new_id(),
                guild_id=guild_id,
                user_id=user_id,
                expires_at=time.monotonic() + self.timeout_seconds,
            )
            self._sessions[sess.session_id] = sess
            self._by_user[existing_key] = sess.session_id
            return sess

    async def get(self, session_id: str) -> Optional[VerificationSession]:
        async with self._lock:
            sess = self._sessions.get(session_id)
            if sess and sess.is_expired() and sess.state not in (VState.COMPLETED, VState.REJECTED):
                if sess.can_transition(VState.EXPIRED):
                    sess.transition(VState.EXPIRED)
            return sess

    async def get_active_for_user(self, guild_id: int, user_id: int) -> Optional[VerificationSession]:
        async with self._lock:
            sid = self._by_user.get((guild_id, user_id))
            if not sid:
                return None
            sess = self._sessions.get(sid)
            if sess and sess.is_expired() and sess.can_transition(VState.EXPIRED):
                sess.transition(VState.EXPIRED)
            return sess

    async def cleanup_expired(self) -> int:
        async with self._lock:
            removed = 0
            for sid, sess in list(self._sessions.items()):
                if sess.is_expired() and sess.state not in (VState.COMPLETED, VState.REJECTED):
                    if sess.can_transition(VState.EXPIRED):
                        try:
                            sess.transition(VState.EXPIRED)
                        except InvalidTransition:
                            pass
                if sess.state in (VState.COMPLETED, VState.REJECTED) and time.monotonic() - sess.last_transition_at > 3600:
                    self._sessions.pop(sid, None)
                    self._by_user.pop((sess.guild_id, sess.user_id), None)
                    removed += 1
            return removed

    async def restore(self, row: dict, now_wall: float) -> Optional[VerificationSession]:
        """Rebuild an in-flight session from a DB row after restart."""
        try:
            state = VState(row["state"])
        except Exception:
            return None
        if state in (VState.COMPLETED, VState.REJECTED, VState.EXPIRED):
            return None

        remaining = float(row["expires_at"]) - now_wall
        if remaining <= 0:
            return None

        sess = VerificationSession(
            session_id=str(row["session_id"]),
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            state=state,
            expires_at=time.monotonic() + remaining,
            risk_score=int(row.get("risk_score") or 0),
            risk_level=str(row.get("risk_level") or "LOW"),
            confidence=float(row.get("confidence") or 0.0),
            layer=int(row.get("layer") or 1),
            assessment_id=int(row.get("assessment_id") or 0) or None,
        )
        async with self._lock:
            self._sessions[sess.session_id] = sess
            self._by_user[(sess.guild_id, sess.user_id)] = sess.session_id
        return sess

    def snapshot_safe(self, sess: VerificationSession) -> str:
        return (
            "session=" + sess.session_id[:8] + "... guild=" + str(sess.guild_id) +
            " user=" + str(sess.user_id) + " state=" + sess.state.value +
            " layer=" + str(sess.layer) + " risk=" + str(sess.risk_score)
        )
