"""Orchestrator. Ties sessions, detectors, engines, and persistence together."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import discord

from bot.database.database import Database
from bot.verification.db import VerificationRepo
from bot.verification.detectors import (
    DetectorContext, DetectorRegistry, DResult, DStatus, Family,
)
from bot.verification.engines import ClusterEngine, HistoricalEngine
from bot.verification.providers import (
    NetworkProvider, NullNetworkProvider, PublicRobloxProvider, RobloxProvider,
)
from bot.verification.rate_limit import RateLimiter, RateLimitExceeded
from bot.verification.redaction import r, rex
from bot.verification.risk import RiskEngine, RiskVerdict, Thresholds
from bot.verification.session import InvalidTransition, SessionManager, VState


# ---------------------------------------------------------------------------
# In-memory behavior tracker (bounded deques per guild)
# ---------------------------------------------------------------------------
@dataclass
class _BehaviorTrackers:
    guild_id: int
    join_times: list[float]
    new_account_joins: list[float]      # joined at time.monotonic()
    verification_times: list[float]
    user_messages: dict[int, list[float]]
    user_mentions: dict[int, set[int]]
    roblox_attempts: dict[int, list[float]]
    network_verifs: dict[str, list[float]]
    role_adds: dict[int, list[float]]


class BehaviorTracker:
    def __init__(self) -> None:
        self._guilds: dict[int, _BehaviorTrackers] = {}

    def _g(self, guild_id: int) -> _BehaviorTrackers:
        g = self._guilds.get(guild_id)
        if g is None:
            g = _BehaviorTrackers(
                guild_id=guild_id,
                join_times=[],
                new_account_joins=[],
                verification_times=[],
                user_messages={},
                user_mentions={},
                roblox_attempts={},
                network_verifs={},
                role_adds={},
            )
            self._guilds[guild_id] = g
        return g

    def record_join(self, guild_id: int, account_age_days: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        g.join_times.append(now)
        cutoff = now - 600
        g.join_times[:] = [t for t in g.join_times if t > cutoff]
        if account_age_days < 7:
            g.new_account_joins.append(now)
            g.new_account_joins[:] = [t for t in g.new_account_joins if t > now - 600]

    def record_verification(self, guild_id: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        g.verification_times.append(now)
        g.verification_times[:] = [t for t in g.verification_times if t > now - 300]

    def record_message(self, guild_id: int, user_id: int, mention_ids: set[int]) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        lst = g.user_messages.setdefault(user_id, [])
        lst.append(now)
        lst[:] = [t for t in lst if t > now - 600]
        s = g.user_mentions.setdefault(user_id, set())
        s.update(mention_ids)

    def record_roblox_attempt(self, guild_id: int, user_id: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        lst = g.roblox_attempts.setdefault(user_id, [])
        lst.append(now)
        lst[:] = [t for t in lst if t > now - 300]

    def record_network(self, guild_id: int, network_id: str) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        lst = g.network_verifs.setdefault(network_id, [])
        lst.append(now)
        lst[:] = [t for t in lst if t > now - 600]

    def record_role_add(self, guild_id: int, user_id: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        lst = g.role_adds.setdefault(user_id, [])
        lst.append(now)
        lst[:] = [t for t in lst if t > now - 3600]

    def snapshot(self, guild_id: int, user_id: int) -> dict[str, Any]:
        g = self._g(guild_id)
        now = time.monotonic()
        return {
            "guild_joins_last_60s": len([t for t in g.join_times if t > now - 60]),
            "guild_new_account_joins_last_300s": len(g.new_account_joins),
            "guild_verifications_last_120s": len([t for t in g.verification_times if t > now - 120]),
            "user_messages_first_10m": len(g.user_messages.get(user_id, [])),
            "user_unique_mentions_first_10m": len(g.user_mentions.get(user_id, set())),
            "user_roblox_attempts_last_5m": len(g.roblox_attempts.get(user_id, [])),
        }

    def network_verifications_last_10m(self, guild_id: int, network_id: str) -> int:
        g = self._g(guild_id)
        now = time.monotonic()
        return len([t for t in g.network_verifs.get(network_id, []) if t > now - 600])

    def user_role_adds_last_1h(self, guild_id: int, user_id: int) -> int:
        g = self._g(guild_id)
        now = time.monotonic()
        return len([t for t in g.role_adds.get(user_id, []) if t > now - 3600])


# ---------------------------------------------------------------------------
# Detector execution
# ---------------------------------------------------------------------------
async def _run_one(det, ctx, timeout=6.0):
    try:
        return await asyncio.wait_for(det.evaluate(ctx), timeout=timeout)
    except asyncio.TimeoutError:
        return DResult(det.id, DStatus.ERROR, False, 0.0, 0.0, 0.0,
                       det.evidence_type, det.family, "detector timeout")
    except Exception as exc:
        return det._error(exc)


async def run_detectors(registry: DetectorRegistry, ctx: DetectorContext,
                        timeout: float = 8.0, max_concurrency: int = 12) -> list[DResult]:
    sem = asyncio.Semaphore(max_concurrency)
    async def wrapped(d):
        async with sem:
            return await _run_one(d, ctx)
    return await asyncio.gather(*(wrapped(d) for d in registry.all()))


# ---------------------------------------------------------------------------
# VerificationService
# ---------------------------------------------------------------------------
class VerificationService:
    def __init__(
        self,
        bot,
        db: Database,
        config_service,
        logging_service,
        *,
        session_timeout: int = 900,
        thresholds: Optional[Thresholds] = None,
        network_provider: Optional[NetworkProvider] = None,
        roblox_provider: Optional[RobloxProvider] = None,
    ) -> None:
        self.bot = bot
        self.db = db
        self.config = config_service
        self.logging = logging_service

        self.sessions = SessionManager(timeout_seconds=session_timeout)
        self.registry = DetectorRegistry()
        self.risk = RiskEngine(thresholds)
        self.repo = VerificationRepo(db)
        self.rate = RateLimiter()
        self.behavior = BehaviorTracker()

        self.network_provider = network_provider or NullNetworkProvider()
        self.roblox_provider = roblox_provider or PublicRobloxProvider()

        self._cluster_fingerprint_index: dict[str, set[int]] = {}
        self._cluster_fingerprint_rarity: dict[str, float] = {}

    # ---- behavior hooks (called from the cog) ----
    def on_member_join(self, member: discord.Member, account_age_days: int) -> None:
        self.behavior.record_join(member.guild.id, account_age_days)

    def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        mention_ids = {m.id for m in message.mentions}
        self.behavior.record_message(message.guild.id, message.author.id, mention_ids)

    def on_role_add(self, guild_id: int, user_id: int) -> None:
        self.behavior.record_role_add(guild_id, user_id)

    # ---- main entry: assess a member ----
    async def assess(self, member: discord.Member, session_id: str,
                     session_started: float) -> RiskVerdict:
        guild_id = member.guild.id
        user_id = member.id
        now = datetime.now(timezone.utc)

        # Account age
        account_age_days = max((now - member.created_at).days, 0)

        # Join age
        join_age = 0
        if member.joined_at:
            join_age = int((now - member.joined_at).total_seconds())

        # History
        history = await self._build_history(member)

        # Roblox lookup (best-effort; never blocks verification on failure)
        roblox = None
        roblox_id = None
        prior_link = await self.repo.latest_assessment(guild_id, user_id)
        linked_roblox = await self._lookup_linked_roblox(guild_id, user_id)
        if linked_roblox:
            roblox_id = linked_roblox
            try:
                roblox = await asyncio.wait_for(
                    self.roblox_provider.lookup_user_by_id(roblox_id), timeout=5.0,
                )
            except Exception:
                roblox = None

        # Network lookup — only if provider is available. Never blocks.
        network = None
        network_id = None
        try:
            network = await asyncio.wait_for(
                self.network_provider.lookup(None), timeout=3.0,
            )
            network_id = network.network_id if network and network.available else None
        except Exception:
            network = None

        if network_id:
            self.behavior.record_network(guild_id, network_id)
            try:
                verdict_json = json.dumps({
                    "vpn": network.vpn, "proxy": network.proxy, "tor": network.tor,
                    "datacenter": network.datacenter, "asn": network.asn,
                    "reputation": network.reputation, "risk_score": network.risk_score,
                })
                await self.repo.record_network_event(guild_id, network_id, user_id, verdict_json)
            except Exception:
                pass

        # Cluster engine
        cluster = ClusterEngine.cluster_for(user_id, self._cluster_fingerprint_index,
                                             self._cluster_fingerprint_rarity)
        history["cluster"] = {"size": len(cluster.member_ids), "confidence": cluster.confidence}

        # Cross-family signal (computed lazily by the engine, but a two-pass
        # approach lets D39 see what the rest of the run produced)
        base_ctx = DetectorContext(
            guild=member.guild,
            member=member,
            session_id=session_id,
            session_started_at=session_started,
            account_age_days=account_age_days,
            join_age_seconds=join_age,
            roblox=roblox,
            roblox_id=roblox_id,
            network=network,
            network_id=network_id,
            history=history,
            behavior=self._behavior_snapshot(guild_id, user_id, network_id),
        )

        results_first = await run_detectors(self.registry, base_ctx)
        triggered_fams = {r.signal_family for r in results_first
                          if r.status == DStatus.TRIGGERED and r.triggered}
        base_ctx.extras["triggered_families"] = triggered_fams
        # D39 needs the triggered families; run it alone to avoid re-running others.
        cross = self.registry.get("CROSS_SIGNAL_CORRELATION")
        if cross is not None:
            replacement = await _run_one(cross, base_ctx)
            results_first = [r for r in results_first if r.detector != cross.id]
            results_first.append(replacement)

        verdict = self.risk.evaluate(results_first)
        verdict.assessment_id = await self.repo.save_assessment(guild_id, user_id, session_id, verdict)
        await self._update_clusters(guild_id, member, verdict)
        return verdict

    # ---- helpers ----
    async def _build_history(self, member: discord.Member) -> dict[str, Any]:
        gid = member.guild.id
        uid = member.id
        hist: dict[str, Any] = {}
        hist["last_username"] = await self.repo.get_history(gid, uid, "username")
        hist["last_display_name"] = await self.repo.get_history(gid, uid, "display_name")

        avatar_url = str(member.display_avatar.url) if member.display_avatar else ""
        avatar_fp = hashlib.sha256(avatar_url.encode("utf-8")).hexdigest()[:32] if avatar_url else ""
        if avatar_fp:
            hist["avatar_seen_users"] = list(self._cluster_fingerprint_index.get("avatar:" + avatar_fp, set()))

        hist["user_recent_failures"] = await self.repo.count_recent_failures(gid, uid, 3600)
        hist["user_rejoin_count_24h"] = await self._rejoin_count(gid, uid)
        hist["user_leave_count_30d"] = await self._leave_count(gid, uid)
        hist["user_prior_quarantines"] = await self.repo.count_user_quarantines(gid, uid)
        hist["user_roblox_failures"] = 0
        hist["user_roblox_link_count"] = await self.repo.roblox_links_for_user(gid, uid)
        hist["roblox_link_prior_users"] = 0
        hist["roblox_cluster_size"] = 0
        hist["ban_evasion_matches"] = 0
        hist["known_abuse_signature_matches"] = 0
        hist["member_fingerprints"] = {}
        hist["known_bad_signals"] = {}
        hist["user_recent_role_adds"] = self.behavior.user_role_adds_last_1h(gid, uid)
        return hist

    def _behavior_snapshot(self, guild_id: int, user_id: int, network_id: Optional[str]) -> dict[str, Any]:
        snap = self.behavior.snapshot(guild_id, user_id)
        if network_id:
            snap["network_verifications_last_10m"] = self.behavior.network_verifications_last_10m(guild_id, network_id)
        return snap

    async def _rejoin_count(self, guild_id: int, user_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS c FROM verification_attempts WHERE guild_id = ? AND user_id = ? AND outcome = 'REJOIN' AND created_at > ?",
            (guild_id, user_id, int(time.time()) - 86400),
        )
        return int(row["c"]) if row else 0

    async def _leave_count(self, guild_id: int, user_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS c FROM verification_attempts WHERE guild_id = ? AND user_id = ? AND outcome = 'LEFT' AND created_at > ?",
            (guild_id, user_id, int(time.time()) - 30 * 86400),
        )
        return int(row["c"]) if row else 0

    async def _lookup_linked_roblox(self, guild_id: int, user_id: int) -> Optional[int]:
        row = await self.db.fetchone(
            "SELECT roblox_id FROM roblox_links WHERE guild_id = ? AND discord_id = ? ORDER BY verified_at DESC LIMIT 1",
            (guild_id, user_id),
        )
        return int(row["roblox_id"]) if row else None

    async def _update_clusters(self, guild_id: int, member: discord.Member, verdict: RiskVerdict) -> None:
        # Build a per-member fingerprint set from observable traits
        fps: set[str] = set()
        url = str(member.display_avatar.url) if member.display_avatar else ""
        if url:
            fps.add("avatar:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32])
        if member.name:
            fps.add("name_norm:" + hashlib.sha256(member.name.lower().encode("utf-8")).hexdigest()[:16])
        # Robin: cluster only on suspicious results
        if verdict.risk_level.value not in ("HIGH", "CRITICAL"):
            return
        for fp in fps:
            ids = self._cluster_fingerprint_index.setdefault(fp, set())
            ids.add(member.id)
            self._cluster_fingerprint_rarity[fp] = 1.0 / max(len(ids), 1)

    # ---- public API ----
    async def create_session(self, guild_id: int, user_id: int):
        try:
            await self.rate.hit(f"session:{guild_id}:{user_id}", limit=5, window_seconds=60)
        except RateLimitExceeded:
            return None
        return await self.sessions.create(guild_id, user_id)

    async def verify(self, guild_id: int, user_id: int, session_id: str) -> RiskVerdict:
        try:
            await self.rate.hit(f"verify:{guild_id}:{user_id}", limit=10, window_seconds=300)
        except RateLimitExceeded as exc:
            raise
        sess = await self.sessions.get(session_id)
        if sess is None or sess.guild_id != guild_id or sess.user_id != user_id:
            raise PermissionError("session mismatch")
        if sess.state in (VState.COMPLETED, VState.REJECTED):
            raise PermissionError("session already finalized")
        if sess.is_expired():
            try:
                sess.transition(VState.EXPIRED)
            except InvalidTransition:
                pass
            raise TimeoutError("session expired")

        try:
            sess.transition(VState.SECURITY_CHECK)
        except InvalidTransition:
            # already in security check
            pass

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise RuntimeError("guild not found")
        member = guild.get_member(user_id)
        if member is None:
            raise RuntimeError("member not found")

        verdict = await self.assess(member, session_id, sess.created_at)
        sess.risk_score = verdict.risk_score
        sess.risk_level = verdict.risk_level.value
        sess.confidence = verdict.confidence
        sess.layer = int(verdict.required_layer.value)
        sess.assessment_id = verdict.assessment_id

        try:
            sess.transition(VState.LAYER_SELECTED)
        except InvalidTransition:
            pass

        self.behavior.record_verification(guild_id)
        await self.repo.save_session(sess)
        await self.repo.record_attempt(guild_id, user_id, session_id, "ASSESSED", sess.layer)
        await self.repo.log_event(guild_id, user_id, "assessment",
                                  f"layer={sess.layer} risk={sess.risk_score} conf={sess.confidence:.2f}")
        return verdict
