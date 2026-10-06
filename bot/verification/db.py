"""Verification schema + repository (uses existing Database wrapper)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from bot.database.database import Database
from bot.verification.detectors import DResult, DStatus
from bot.verification.risk import RiskVerdict


SCHEMA: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS verification_sessions (
        session_id TEXT PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        state TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        risk_score INTEGER DEFAULT 0,
        risk_level TEXT DEFAULT 'LOW',
        confidence REAL DEFAULT 0.0,
        layer INTEGER DEFAULT 1,
        assessment_id INTEGER DEFAULT 0,
        attempts INTEGER DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vsessions_guild_user ON verification_sessions(guild_id, user_id)",
    """
    CREATE TABLE IF NOT EXISTS verification_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        outcome TEXT NOT NULL,
        layer INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vattempts_guild_user ON verification_attempts(guild_id, user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS risk_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        risk_score INTEGER NOT NULL,
        risk_level TEXT NOT NULL,
        confidence REAL NOT NULL,
        required_layer INTEGER NOT NULL,
        recommendation TEXT,
        detections_json TEXT,
        families_json TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_risk_guild_user ON risk_assessments(guild_id, user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS roblox_links (
        guild_id INTEGER NOT NULL,
        discord_id INTEGER NOT NULL,
        roblox_id INTEGER NOT NULL,
        roblox_name TEXT,
        verified_at INTEGER NOT NULL,
        PRIMARY KEY (guild_id, discord_id, roblox_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_roblox_by_rbx ON roblox_links(guild_id, roblox_id)",
    """
    CREATE TABLE IF NOT EXISTS network_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        network_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        verdict_json TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_net_by_id ON network_events(guild_id, network_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS account_history (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS account_clusters (
        cluster_id TEXT PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        member_ids TEXT NOT NULL,
        confidence REAL NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS manual_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        assessment_id INTEGER,
        decision TEXT NOT NULL,
        moderator_id INTEGER NOT NULL,
        note TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_mr_guild_user ON manual_reviews(guild_id, user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER,
        kind TEXT NOT NULL,
        detail TEXT,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_se_guild_kind ON security_events(guild_id, kind, created_at DESC)",
]


async def ensure_schema(db: Database) -> None:
    for stmt in SCHEMA:
        await db.execute(stmt)


def _now() -> int:
    return int(time.time())


class VerificationRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- sessions ----
    async def save_session(self, sess) -> None:
        await self.db.execute(
            """INSERT INTO verification_sessions
               (session_id, guild_id, user_id, state, created_at, expires_at, risk_score,
                risk_level, confidence, layer, assessment_id, attempts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 state=excluded.state, risk_score=excluded.risk_score,
                 risk_level=excluded.risk_level, confidence=excluded.confidence,
                 layer=excluded.layer, assessment_id=excluded.assessment_id,
                 attempts=excluded.attempts, expires_at=excluded.expires_at""",
            sess.to_row(),
        )

    async def load_incomplete_sessions(self, guild_id: int) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT * FROM verification_sessions
               WHERE guild_id = ? AND state NOT IN ('COMPLETED','REJECTED','EXPIRED')""",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    # ---- attempts ----
    async def record_attempt(self, guild_id: int, user_id: int, session_id: str, outcome: str, layer: int) -> None:
        await self.db.execute(
            """INSERT INTO verification_attempts
               (guild_id, user_id, session_id, outcome, layer, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, session_id, outcome, layer, _now()),
        )

    async def count_recent_failures(self, guild_id: int, user_id: int, seconds: int = 3600) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(*) AS c FROM verification_attempts
               WHERE guild_id = ? AND user_id = ? AND outcome = 'FAILED' AND created_at > ?""",
            (guild_id, user_id, _now() - seconds),
        )
        return int(row["c"]) if row else 0

    # ---- risk assessments ----
    async def save_assessment(self, guild_id: int, user_id: int, session_id: str, verdict: RiskVerdict) -> int:
        detections = [
            {
                "detector": r.detector,
                "status": r.status.value,
                "triggered": r.triggered,
                "severity": round(r.severity, 4),
                "confidence": round(r.confidence, 4),
                "family": r.signal_family.value,
                "evidence_type": r.evidence_type,
                "safe_reason": r.safe_reason,
            }
            for r in verdict.detections
        ]
        families = [f.value for f in verdict.triggered_families]
        await self.db.execute(
            """INSERT INTO risk_assessments
               (guild_id, user_id, session_id, risk_score, risk_level, confidence,
                required_layer, recommendation, detections_json, families_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, session_id, verdict.risk_score, verdict.risk_level.value,
             verdict.confidence, int(verdict.required_layer.value), verdict.recommendation,
             json.dumps(detections), json.dumps(families), _now()),
        )
        row = await self.db.fetchone("SELECT last_insert_rowid() AS id")
        return int(row["id"]) if row else 0

    async def latest_assessment(self, guild_id: int, user_id: int) -> Optional[dict]:
        row = await self.db.fetchone(
            """SELECT * FROM risk_assessments WHERE guild_id = ? AND user_id = ?
               ORDER BY id DESC LIMIT 1""",
            (guild_id, user_id),
        )
        return dict(row) if row else None

    # ---- roblox links ----
    async def save_roblox_link(self, guild_id: int, discord_id: int, roblox_id: int, roblox_name: str) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO roblox_links
               (guild_id, discord_id, roblox_id, roblox_name, verified_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, discord_id, roblox_id, roblox_name, _now()),
        )

    async def roblox_link_prior_users(self, guild_id: int, roblox_id: int, exclude_discord_id: int) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(DISTINCT discord_id) AS c FROM roblox_links
               WHERE guild_id = ? AND roblox_id = ? AND discord_id != ?""",
            (guild_id, roblox_id, exclude_discord_id),
        )
        return int(row["c"]) if row else 0

    async def roblox_links_for_user(self, guild_id: int, discord_id: int) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(DISTINCT roblox_id) AS c FROM roblox_links
               WHERE guild_id = ? AND discord_id = ?""",
            (guild_id, discord_id),
        )
        return int(row["c"]) if row else 0

    # ---- network events ----
    async def record_network_event(self, guild_id: int, network_id: str, user_id: int, verdict_json: str) -> None:
        await self.db.execute(
            """INSERT INTO network_events (guild_id, network_id, user_id, verdict_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, network_id, user_id, verdict_json, _now()),
        )

    async def network_recent_users(self, guild_id: int, network_id: str, seconds: int = 600) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(DISTINCT user_id) AS c FROM network_events
               WHERE guild_id = ? AND network_id = ? AND created_at > ?""",
            (guild_id, network_id, _now() - seconds),
        )
        return int(row["c"]) if row else 0

    async def network_recent_count(self, guild_id: int, network_id: str, seconds: int = 600) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(*) AS c FROM network_events
               WHERE guild_id = ? AND network_id = ? AND created_at > ?""",
            (guild_id, network_id, _now() - seconds),
        )
        return int(row["c"]) if row else 0

    # ---- account history ----
    async def set_history(self, guild_id: int, user_id: int, key: str, value: str) -> None:
        await self.db.execute(
            """INSERT INTO account_history (guild_id, user_id, key, value, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, user_id, key) DO UPDATE SET
                 value=excluded.value, updated_at=excluded.updated_at""",
            (guild_id, user_id, key, value, _now()),
        )

    async def get_history(self, guild_id: int, user_id: int, key: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT value FROM account_history WHERE guild_id = ? AND user_id = ? AND key = ?",
            (guild_id, user_id, key),
        )
        return row["value"] if row else None

    # ---- manual reviews ----
    async def record_review(self, guild_id: int, user_id: int, assessment_id: Optional[int],
                            decision: str, moderator_id: int, note: str) -> None:
        await self.db.execute(
            """INSERT INTO manual_reviews
               (guild_id, user_id, assessment_id, decision, moderator_id, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, assessment_id or 0, decision, moderator_id, note, _now()),
        )

    async def count_user_quarantines(self, guild_id: int, user_id: int) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(*) AS c FROM manual_reviews
               WHERE guild_id = ? AND user_id = ? AND decision = 'QUARANTINE'""",
            (guild_id, user_id),
        )
        return int(row["c"]) if row else 0

    # ---- security events ----
    async def log_event(self, guild_id: int, user_id: Optional[int], kind: str, detail: str) -> None:
        await self.db.execute(
            "INSERT INTO security_events (guild_id, user_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id or 0, kind, detail, _now()),
        )
