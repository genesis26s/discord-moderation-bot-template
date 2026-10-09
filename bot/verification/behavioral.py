"""Behavioral tracking: presence, voice, activity - for session correlation.

Stores only state transitions and channel/activity names. No content, no IPs,
no emails, no message text. Raw events retain for 14 days.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Optional

import discord

from bot.database.database import Database
from bot.verification.redaction import rex

log = logging.getLogger(__name__)


def _is_present(status) -> bool:
    """True if the member is connected to the gateway (not offline)."""
    try:
        return str(status) != "offline"
    except Exception:
        return False


def _extract_activity_keys(activities) -> set:
    """Return a set of 'type:name' fingerprints from an activity list."""
    keys: set = set()
    for a in activities or []:
        try:
            t = getattr(a, "type", None)
            n = getattr(a, "name", None)
            if t is None or not n:
                continue
            tname = getattr(t, "name", None) or str(t)
            tname = str(tname).lower()
            if tname in ("custom", "unknown"):
                continue
            keys.add(tname + ":" + str(n).lower()[:200])
        except Exception:
            continue
    return keys


class BehavioralTracker:
    """Records presence / voice / activity state transitions into the DB.

    Only stores transitions (changes), not repeated identical states.
    """

    RETENTION_DAYS = 14

    def __init__(self, db: Database) -> None:
        self.db = db

    async def record_presence(self, member: discord.Member,
                              before_status, after_status) -> None:
        if member.bot or member.guild is None:
            return
        was = _is_present(before_status)
        now = _is_present(after_status)
        if was == now:
            return
        state = "online" if now else "offline"
        try:
            await self.db.execute(
                "INSERT INTO presence_events (guild_id, user_id, state, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (member.guild.id, member.id, state, int(time.time())),
            )
        except Exception as exc:
            log.warning("presence write failed: %s", rex(exc))

    async def record_voice(self, member: discord.Member,
                           before_channel, after_channel) -> None:
        if member.bot or member.guild is None:
            return
        before_id = getattr(before_channel, "id", None)
        after_id = getattr(after_channel, "id", None)
        if before_id == after_id:
            return
        now = int(time.time())
        try:
            if before_id is not None:
                await self.db.execute(
                    "INSERT INTO voice_events (guild_id, user_id, channel_id, event_type, timestamp) "
                    "VALUES (?, ?, ?, 'leave', ?)",
                    (member.guild.id, member.id, before_id, now),
                )
            if after_id is not None:
                await self.db.execute(
                    "INSERT INTO voice_events (guild_id, user_id, channel_id, event_type, timestamp) "
                    "VALUES (?, ?, ?, 'join', ?)",
                    (member.guild.id, member.id, after_id, now),
                )
        except Exception as exc:
            log.warning("voice write failed: %s", rex(exc))

    async def record_activities(self, member: discord.Member,
                                before_activities, after_activities) -> None:
        if member.bot or member.guild is None:
            return
        before_keys = _extract_activity_keys(before_activities)
        after_keys = _extract_activity_keys(after_activities)
        new_keys = after_keys - before_keys
        if not new_keys:
            return
        now = int(time.time())
        for key in new_keys:
            try:
                atype, aname = key.split(":", 1)
            except ValueError:
                continue
            try:
                await self.db.execute(
                    "INSERT INTO activity_events (guild_id, user_id, activity_type, activity_name, timestamp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (member.guild.id, member.id, atype, aname, now),
                )
            except Exception as exc:
                log.warning("activity write failed: %s", rex(exc))

    async def cleanup_old_events(self) -> int:
        """Delete events older than RETENTION_DAYS. Returns rows removed."""
        cutoff = int(time.time()) - (self.RETENTION_DAYS * 86400)
        total = 0
        for table in ("presence_events", "voice_events", "activity_events"):
            try:
                n = await self.db.execute(
                    "DELETE FROM " + table + " WHERE timestamp < ?",
                    (cutoff,),
                )
                if isinstance(n, int):
                    total += n
            except Exception as exc:
                log.warning("cleanup failed for %s: %s", table, rex(exc))
        return total


class SessionCorrelator:
    """Computes behavioural correlations between members.

    For a given member X, loads X's event stream and compares it against
    the N most recent other members' event streams. Returns the strongest
    match per dimension (presence / voice / activity / session start).
    """

    CANDIDATE_LIMIT = 50
    WINDOW_DAYS = 14

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    async def presence_correlation(self, guild_id: int, user_id: int) -> Optional[dict]:
        own = await self._load_presence(guild_id, user_id)
        if len(own) < 4:
            return None
        candidates = await self._load_presence_candidates(guild_id, user_id)
        best = None
        for cand_id, cand_events in candidates.items():
            if len(cand_events) < 4:
                continue
            overlap, handover = self._compare_presence(own, cand_events)
            score = max(overlap, handover)
            if score >= 0.6 and (best is None or score > best["score"]):
                best = {
                    "user_id": cand_id,
                    "score": round(score, 3),
                    "overlap": round(overlap, 3),
                    "handover": round(handover, 3),
                }
        return best

    async def voice_correlation(self, guild_id: int, user_id: int) -> Optional[dict]:
        own_channels = await self._load_voice_channels(guild_id, user_id)
        if not own_channels:
            return None
        # favourite channels of X (top 3)
        top_own = sorted(own_channels.items(), key=lambda kv: kv[1], reverse=True)[:3]
        top_own_ids = {cid for cid, _ in top_own}
        if not top_own_ids:
            return None

        candidates = await self._load_voice_candidates(guild_id, user_id)
        best = None
        for cand_id, cand_channels in candidates.items():
            if not cand_channels:
                continue
            top_cand = set(
                cid for cid, _ in sorted(cand_channels.items(), key=lambda kv: kv[1], reverse=True)[:3]
            )
            shared = top_own_ids & top_cand
            if not shared:
                continue
            # overlap of channel sets, weighted by visit count
            overlap_score = len(shared) / max(len(top_own_ids), 1)
            # boost when both use the same *single* channel heavily
            if len(shared) == 1 and len(top_own_ids) == 1:
                overlap_score = 1.0
            if overlap_score >= 0.5 and (best is None or overlap_score > best["score"]):
                best = {
                    "user_id": cand_id,
                    "score": round(overlap_score, 3),
                    "shared_channels": len(shared),
                }
        return best

    async def session_cluster(self, guild_id: int, user_id: int) -> Optional[dict]:
        """Count days where this user logged in within 3min of another user."""
        own_starts = await self._load_session_starts(guild_id, user_id)
        if len(own_starts) < 3:
            return None
        candidates = await self._load_session_starts_candidates(guild_id, user_id)
        best = None
        for cand_id, cand_starts in candidates.items():
            if len(cand_starts) < 3:
                continue
            days = self._count_matched_days(own_starts, cand_starts, window_seconds=180)
            if days >= 3 and (best is None or days > best["days"]):
                best = {"user_id": cand_id, "days": days}
        return best

    async def activity_overlap(self, guild_id: int, user_id: int) -> Optional[dict]:
        own = await self._load_activities(guild_id, user_id)
        if not own:
            return None
        # exclude the top-10 most common activity names in the guild (music, LoL, Minecraft, etc.)
        common = await self._common_activities(guild_id, limit=10)
        own_filtered = {name: ts for name, ts in own.items() if name not in common}
        if not own_filtered:
            return None
        candidates = await self._load_activity_candidates(guild_id, user_id, exclude=common)
        best = None
        for cand_id, cand_acts in candidates.items():
            shared = set(own_filtered.keys()) & set(cand_acts.keys())
            if len(shared) >= 1:
                score = min(len(shared) / 3.0, 1.0)
                if score >= 0.33 and (best is None or score > best["score"]):
                    best = {
                        "user_id": cand_id,
                        "score": round(score, 3),
                        "shared": list(shared)[:3],
                    }
        return best

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    async def _load_presence(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT state, timestamp FROM presence_events "
            "WHERE guild_id = ? AND user_id = ? AND timestamp > ? "
            "ORDER BY timestamp",
            (guild_id, user_id, cutoff),
        )
        return [(str(r["state"]), int(r["timestamp"])) for r in rows]

    async def _load_presence_candidates(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT DISTINCT user_id FROM presence_events "
            "WHERE guild_id = ? AND user_id != ? AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (guild_id, user_id, cutoff, self.CANDIDATE_LIMIT),
        )
        ids = [int(r["user_id"]) for r in rows]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        evs = await self.db.fetchall(
            f"SELECT user_id, state, timestamp FROM presence_events "
            f"WHERE guild_id = ? AND user_id IN ({placeholders}) AND timestamp > ? "
            f"ORDER BY user_id, timestamp",
            (guild_id, *ids, cutoff),
        )
        out: dict[int, list] = defaultdict(list)
        for r in evs:
            out[int(r["user_id"])].append((str(r["state"]), int(r["timestamp"])))
        return out

    async def _load_voice_channels(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT channel_id, COUNT(*) AS c FROM voice_events "
            "WHERE guild_id = ? AND user_id = ? AND event_type = 'join' AND timestamp > ? "
            "GROUP BY channel_id",
            (guild_id, user_id, cutoff),
        )
        return {int(r["channel_id"]): int(r["c"]) for r in rows if r["channel_id"] is not None}

    async def _load_voice_candidates(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT DISTINCT user_id FROM voice_events "
            "WHERE guild_id = ? AND user_id != ? AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (guild_id, user_id, cutoff, self.CANDIDATE_LIMIT),
        )
        ids = [int(r["user_id"]) for r in rows]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        evs = await self.db.fetchall(
            f"SELECT user_id, channel_id, COUNT(*) AS c FROM voice_events "
            f"WHERE guild_id = ? AND user_id IN ({placeholders}) AND event_type = 'join' AND timestamp > ? "
            f"GROUP BY user_id, channel_id",
            (guild_id, *ids, cutoff),
        )
        out: dict[int, dict] = defaultdict(dict)
        for r in evs:
            if r["channel_id"] is not None:
                out[int(r["user_id"])][int(r["channel_id"])] = int(r["c"])
        return out

    async def _load_session_starts(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT state, timestamp FROM presence_events "
            "WHERE guild_id = ? AND user_id = ? AND timestamp > ? "
            "ORDER BY timestamp",
            (guild_id, user_id, cutoff),
        )
        starts = []
        prev_state = "offline"
        for r in rows:
            s = str(r["state"])
            if prev_state == "offline" and s == "online":
                starts.append(int(r["timestamp"]))
            prev_state = s
        return starts

    async def _load_session_starts_candidates(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT DISTINCT user_id FROM presence_events "
            "WHERE guild_id = ? AND user_id != ? AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (guild_id, user_id, cutoff, self.CANDIDATE_LIMIT),
        )
        ids = [int(r["user_id"]) for r in rows]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        evs = await self.db.fetchall(
            f"SELECT user_id, state, timestamp FROM presence_events "
            f"WHERE guild_id = ? AND user_id IN ({placeholders}) AND timestamp > ? "
            f"ORDER BY user_id, timestamp",
            (guild_id, *ids, cutoff),
        )
        out: dict[int, list] = defaultdict(list)
        prev_by_user: dict[int, str] = {}
        for r in evs:
            uid = int(r["user_id"])
            s = str(r["state"])
            if prev_by_user.get(uid, "offline") == "offline" and s == "online":
                out[uid].append(int(r["timestamp"]))
            prev_by_user[uid] = s
        return out

    async def _load_activities(self, guild_id: int, user_id: int):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT activity_name, MAX(timestamp) AS ts FROM activity_events "
            "WHERE guild_id = ? AND user_id = ? AND timestamp > ? "
            "GROUP BY activity_name",
            (guild_id, user_id, cutoff),
        )
        return {str(r["activity_name"]): int(r["ts"]) for r in rows}

    async def _load_activity_candidates(self, guild_id: int, user_id: int, exclude: set):
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT DISTINCT user_id FROM activity_events "
            "WHERE guild_id = ? AND user_id != ? AND timestamp > ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (guild_id, user_id, cutoff, self.CANDIDATE_LIMIT),
        )
        ids = [int(r["user_id"]) for r in rows]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        evs = await self.db.fetchall(
            f"SELECT user_id, activity_name FROM activity_events "
            f"WHERE guild_id = ? AND user_id IN ({placeholders}) AND timestamp > ?",
            (guild_id, *ids, cutoff),
        )
        out: dict[int, dict] = defaultdict(dict)
        for r in evs:
            name = str(r["activity_name"])
            if name in exclude:
                continue
            out[int(r["user_id"])][name] = 1
        return out

    async def _common_activities(self, guild_id: int, limit: int = 10) -> set:
        cutoff = int(time.time()) - self.WINDOW_DAYS * 86400
        rows = await self.db.fetchall(
            "SELECT activity_name, COUNT(DISTINCT user_id) AS c FROM activity_events "
            "WHERE guild_id = ? AND timestamp > ? "
            "GROUP BY activity_name ORDER BY c DESC LIMIT ?",
            (guild_id, cutoff, limit),
        )
        return {str(r["activity_name"]) for r in rows}

    # ------------------------------------------------------------------
    # Math
    # ------------------------------------------------------------------
    @staticmethod
    def _to_intervals(events: list) -> list:
        out = []
        for i, (state, ts) in enumerate(events):
            end = events[i + 1][1] if i + 1 < len(events) else ts + 3600
            out.append((ts, end, state))
        return out

    @staticmethod
    def _compare_presence(a: list, b: list) -> tuple:
        ai = SessionCorrelator._to_intervals(a)
        bi = SessionCorrelator._to_intervals(b)

        def present(state: str) -> bool:
            return state == "online"

        a_present_secs = sum(e - s for s, e, st in ai if present(st))
        b_present_secs = sum(e - s for s, e, st in bi if present(st))
        if a_present_secs <= 0 or b_present_secs <= 0:
            return 0.0, 0.0

        overlap_secs = 0
        for sa, ea, sta in ai:
            if not present(sta):
                continue
            for sb, eb, stb in bi:
                if not present(stb):
                    continue
                lo = max(sa, sb)
                hi = min(ea, eb)
                if hi > lo:
                    overlap_secs += hi - lo
        smaller = min(a_present_secs, b_present_secs)
        overlap = overlap_secs / smaller if smaller > 0 else 0.0

        # handovers: A goes offline within 60s of B coming online
        handovers = 0
        a_off = []
        for i in range(1, len(ai)):
            if present(ai[i - 1][2]) and not present(ai[i][2]):
                a_off.append(ai[i][0])
        b_on = []
        for i in range(1, len(bi)):
            if not present(bi[i - 1][2]) and present(bi[i][2]):
                b_on.append(bi[i][0])
        for off_t in a_off:
            for on_t in b_on:
                if abs(off_t - on_t) <= 60:
                    handovers += 1
                    break
        # normalization: 5+ handovers = max
        handover = min(handovers / 5.0, 1.0)
        return min(overlap, 1.0), handover

    @staticmethod
    def _count_matched_days(a_starts: list, b_starts: list, window_seconds: int) -> int:
        from datetime import datetime, timezone
        matched_days = set()
        for ta in a_starts:
            for tb in b_starts:
                if abs(ta - tb) <= window_seconds:
                    day = datetime.fromtimestamp(ta, tz=timezone.utc).strftime("%Y-%m-%d")
                    matched_days.add(day)
                    break
        return len(matched_days)
