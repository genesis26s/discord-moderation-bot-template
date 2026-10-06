"""Verification sessions with strict state machine."""
from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from bot.verification.redaction import r


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


# Legal transitions. Anything not listed here is rejected.
_TRANSITIONS: dict[VState, set[VState]] = {
    VState.CREATED: {VState.SECURITY_CHECK, VState.EXPIRED, VState.FAILED},
    VState.SECURITY_CHECK: {VState.LAYER_SELECTED, VState.MANUAL_REVIEW, VState.EXPIRED, VState.FAILED},
    VState.LAYER_SELECTED: {VState.CHALLENGE_REQUIRED, VState.QUARANTINED, VState.MANUAL_REVIEW, VState.EXPIRED},
    VState.CHALLENGE_REQUIRED: {VState.CHALLENGE_ACTIVE, VState.EXPIRED, VState.FAILED},
    VState.CHALLENGE_ACTIVE: {VState.COMPLETED, VState.FAILED, VState.EXPIRED, VState.MANUAL_REVIEW},
    VState.COMPLETED: set(),
    VState.FAILED: {VState.CREATED},       # allow a fresh attempt
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
    notes: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.monotonic() > self.expires_at

    def can_transition(self, target: VState) -> bool:
        return target in _TRANSITIONS.get(self.state, set())

    def transition(self, target: VState) -> None:
        if not self.can_transition(target):
            raise InvalidTransition(f"Cannot move from {self.state.value} to {target.value}")
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
    """In-memory sessions + DB persistence for restart recovery."""

    def __init__(self, timeout_seconds: int = 900) -> None:
        self._sessions: dict[str, VerificationSession] = {}
        self._by_user: dict[tuple[int, int], str] = {}
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
                    return sess  # reuse in-flight session
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

    def snapshot_safe(self, sess: VerificationSession) -> str:
        return (
            f"session={sess.session_id[:8]}... guild={sess.guild_id} user={sess.user_id} "
            f"state={sess.state.value} layer={sess.layer} risk={sess.risk_score} conf={sess.confidence:.2f}"
        )
