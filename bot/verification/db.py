"""Verification schema + repository."""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from bot.database.database import Database


SCHEMA: list[str] = [
    """CREATE TABLE IF NOT EXISTS verification_sessions (
        session_id TEXT PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        state TEXT NOT NULL, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        risk_score INTEGER DEFAULT 0, risk_level TEXT DEFAULT 'LOW', confidence REAL DEFAULT 0.0,
        layer INTEGER DEFAULT 1, assessment_id INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_vsessions_guild_user ON verification_sessions(guild_id, user_id)",
    """CREATE TABLE IF NOT EXISTS verification_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        session_id TEXT NOT NULL, outcome TEXT NOT NULL, layer INTEGER NOT NULL, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_vattempts_guild_user ON verification_attempts(guild_id, user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_vattempts_outcome ON verification_attempts(guild_id, user_id, outcome, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS risk_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        session_id TEXT NOT NULL, risk_score INTEGER NOT NULL, risk_level TEXT NOT NULL,
        confidence REAL NOT NULL, required_layer INTEGER NOT NULL, recommendation TEXT,
        detections_json TEXT, families_json TEXT, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_risk_guild_user ON risk_assessments(guild_id, user_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS roblox_links (
        guild_id INTEGER NOT NULL, discord_id INTEGER NOT NULL, roblox_id INTEGER NOT NULL,
        roblox_name TEXT, verified_at INTEGER NOT NULL,
        PRIMARY KEY (guild_id, discord_id, roblox_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_roblox_by_rbx ON roblox_links(guild_id, roblox_id)",
    """CREATE TABLE IF NOT EXISTS network_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, network_id TEXT NOT NULL,
        user_id INTEGER NOT NULL, verdict_json TEXT, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_net_by_id ON network_events(guild_id, network_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS account_history (
        guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, key TEXT NOT NULL,
        value TEXT, updated_at INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id, key)
    )""",
    """CREATE TABLE IF NOT EXISTS account_clusters (
        cluster_id TEXT PRIMARY KEY, guild_id INTEGER NOT NULL, member_ids TEXT NOT NULL,
        confidence REAL NOT NULL, updated_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_clusters_guild ON account_clusters(guild_id, updated_at DESC)",
    """CREATE TABLE IF NOT EXISTS manual_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        assessment_id INTEGER, decision TEXT NOT NULL, moderator_id INTEGER NOT NULL,
        note TEXT, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mr_guild_user ON manual_reviews(guild_id, user_id, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER,
        kind TEXT NOT NULL, detail TEXT, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_se_guild_kind ON security_events(guild_id, kind, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS ban_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        username TEXT, display_name TEXT, avatar_hash TEXT, name_hash TEXT,
        reason TEXT, banned_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_banhash ON ban_history(guild_id, avatar_hash)",
    "CREATE INDEX IF NOT EXISTS idx_bannamehash ON ban_history(guild_id, name_hash)",
    """CREATE TABLE IF NOT EXISTS abuse_signatures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        signature_key TEXT NOT NULL, signature_value TEXT NOT NULL,
        weight REAL DEFAULT 1.0, created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_abusesig ON abuse_signatures(guild_id, signature_key)",
    """CREATE TABLE IF NOT EXISTS pending_reviews (
        message_id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        assessment_id INTEGER,
        created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pending_guild_user ON pending_reviews(guild_id, user_id)",
    # ---- Behavioural event tables (Phase 1) ----
    """CREATE TABLE IF NOT EXISTS presence_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        state TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_presence_guild_user_time ON presence_events(guild_id, user_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_presence_guild_time ON presence_events(guild_id, timestamp DESC)",
    """CREATE TABLE IF NOT EXISTS voice_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        channel_id INTEGER,
        event_type TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_voice_guild_user_time ON voice_events(guild_id, user_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_voice_guild_time ON voice_events(guild_id, timestamp DESC)",
    """CREATE TABLE IF NOT EXISTS activity_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        activity_type TEXT NOT NULL,
        activity_name TEXT NOT NULL,
        timestamp INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_activity_guild_time ON activity_events(guild_id, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_activity_guild_user_time ON activity_events(guild_id, user_id, timestamp DESC)",
]


async def ensure_schema(db: Database) -> None:
    for stmt in SCHEMA:
        await db.execute(stmt)


def _now() -> int:
    return int(time.time())


class VerificationRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

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

    async def load_incomplete_sessions(self, guild_id: int) -> list:
        rows = await self.db.fetchall(
            """SELECT * FROM verification_sessions
               WHERE guild_id = ? AND state NOT IN ('COMPLETED','REJECTED','EXPIRED')""",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def record_attempt(self, guild_id: int, user_id: int, session_id: str,
                             outcome: str, layer: int) -> None:
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

    async def count_recent_outcome(self, guild_id: int, user_id: int, outcome: str, seconds: int) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(*) AS c FROM verification_attempts
               WHERE guild_id = ? AND user_id = ? AND outcome = ? AND created_at > ?""",
            (guild_id, user_id, outcome, _now() - seconds),
        )
        return int(row["c"]) if row else 0

    async def save_assessment(self, guild_id: int, user_id: int, session_id: str, verdict) -> int:
        detections = [
            {"detector": r.detector, "status": r.status.value, "triggered": r.triggered,
             "severity": round(r.severity, 4), "confidence": round(r.confidence, 4),
             "family": r.signal_family.value, "evidence_type": r.evidence_type,
             "safe_reason": r.safe_reason}
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

    async def history_assessments(self, guild_id: int, user_id: int, limit: int = 20) -> list:
        rows = await self.db.fetchall(
            """SELECT id, risk_score, risk_level, confidence, required_layer,
                      recommendation, created_at
               FROM risk_assessments
               WHERE guild_id = ? AND user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )
        return [dict(r) for r in rows]

    # ---- roblox ----
    async def save_roblox_link(self, guild_id: int, discord_id: int,
                               roblox_id: int, roblox_name: str) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO roblox_links
               (guild_id, discord_id, roblox_id, roblox_name, verified_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, discord_id, roblox_id, roblox_name, _now()),
        )

    async def delete_roblox_link(self, guild_id: int, discord_id: int) -> None:
        await self.db.execute(
            "DELETE FROM roblox_links WHERE guild_id = ? AND discord_id = ?",
            (guild_id, discord_id),
        )

    async def get_roblox_link(self, guild_id: int, discord_id: int) -> Optional[dict]:
        row = await self.db.fetchone(
            """SELECT * FROM roblox_links WHERE guild_id = ? AND discord_id = ?
               ORDER BY verified_at DESC LIMIT 1""",
            (guild_id, discord_id),
        )
        return dict(row) if row else None

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

    async def roblox_cluster_size(self, guild_id: int, roblox_id: int) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(DISTINCT discord_id) AS c FROM roblox_links
               WHERE guild_id = ? AND roblox_id = ?""",
            (guild_id, roblox_id),
        )
        return int(row["c"]) if row else 0

    # ---- network ----
    async def record_network_event(self, guild_id: int, network_id: str,
                                   user_id: int, verdict_json: str) -> None:
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

    async def avatar_hash_seen_users(self, guild_id: int, avatar_hash: str,
                                     exclude_user_id: int) -> list:
        rows = await self.db.fetchall(
            """SELECT user_id FROM account_history
               WHERE guild_id = ? AND key = 'avatar_hash' AND value = ? AND user_id != ?""",
            (guild_id, avatar_hash, exclude_user_id),
        )
        return [int(r["user_id"]) for r in rows]

    async def all_avatar_hashes(self, guild_id: int) -> list:
        rows = await self.db.fetchall(
            "SELECT user_id, value FROM account_history WHERE guild_id = ? AND key = 'avatar_hash'",
            (guild_id,),
        )
        return [(int(r["user_id"]), str(r["value"])) for r in rows]

    async def all_name_hashes(self, guild_id: int) -> list:
        rows = await self.db.fetchall(
            "SELECT user_id, value FROM account_history WHERE guild_id = ? AND key = 'name_hash'",
            (guild_id,),
        )
        return [(int(r["user_id"]), str(r["value"])) for r in rows]

    # ---- ban history ----
    async def record_ban(self, guild_id: int, user_id: int, username: str, display_name: str,
                         avatar_hash: str, name_hash: str, reason: str) -> None:
        await self.db.execute(
            """INSERT INTO ban_history
               (guild_id, user_id, username, display_name, avatar_hash, name_hash, reason, banned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, display_name, avatar_hash, name_hash, reason, _now()),
        )

    async def ban_hash_matches(self, guild_id: int, avatar_hash: str, name_hash: str) -> int:
        count = 0
        if avatar_hash:
            row = await self.db.fetchone(
                "SELECT COUNT(*) AS c FROM ban_history WHERE guild_id = ? AND avatar_hash = ?",
                (guild_id, avatar_hash),
            )
            if row:
                count += int(row["c"])
        if name_hash:
            row = await self.db.fetchone(
                "SELECT COUNT(*) AS c FROM ban_history WHERE guild_id = ? AND name_hash = ?",
                (guild_id, name_hash),
            )
            if row:
                count += int(row["c"])
        return count

    # ---- abuse signatures ----
    async def add_signature(self, guild_id: int, key: str, value: str, weight: float = 1.0) -> None:
        await self.db.execute(
            """INSERT INTO abuse_signatures (guild_id, signature_key, signature_value, weight, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (guild_id, key, value, weight, _now()),
        )

    async def remove_signature(self, guild_id: int, key: str, value: str) -> int:
        return await self.db.execute(
            "DELETE FROM abuse_signatures WHERE guild_id = ? AND signature_key = ? AND signature_value = ?",
            (guild_id, key, value),
        )

    async def list_signatures(self, guild_id: int) -> list:
        rows = await self.db.fetchall(
            "SELECT * FROM abuse_signatures WHERE guild_id = ? ORDER BY id DESC",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def match_signatures(self, guild_id: int, values: dict) -> int:
        count = 0
        for k, v in values.items():
            if not v:
                continue
            row = await self.db.fetchone(
                "SELECT COUNT(*) AS c FROM abuse_signatures WHERE guild_id = ? AND signature_key = ? AND signature_value = ?",
                (guild_id, k, v),
            )
            if row:
                count += int(row["c"])
        return count

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

    async def list_reviews(self, guild_id: int, user_id: int, limit: int = 20) -> list:
        rows = await self.db.fetchall(
            """SELECT * FROM manual_reviews WHERE guild_id = ? AND user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (guild_id, user_id, limit),
        )
        return [dict(r) for r in rows]

    # ---- security events ----
    async def log_event(self, guild_id: int, user_id: Optional[int], kind: str, detail: str) -> None:
        await self.db.execute(
            "INSERT INTO security_events (guild_id, user_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id or 0, kind, detail, _now()),
        )

    # ---- pending review panels ----
    async def save_pending_review(self, message_id: int, guild_id: int,
                                  user_id: int, assessment_id) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO pending_reviews
               (message_id, guild_id, user_id, assessment_id, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (message_id, guild_id, user_id, assessment_id or 0, _now()),
        )

    async def get_pending_review(self, message_id: int) -> Optional[dict]:
        row = await self.db.fetchone(
            "SELECT * FROM pending_reviews WHERE message_id = ?",
            (message_id,),
        )
        return dict(row) if row else None

    async def delete_pending_review(self, message_id: int) -> None:
        await self.db.execute(
            "DELETE FROM pending_reviews WHERE message_id = ?",
            (message_id,),
        )
