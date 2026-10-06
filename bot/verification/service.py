"""Verification orchestrator."""
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
from bot.verification.risk import RiskEngine, RiskVerdict, Thresholds
from bot.verification.session import InvalidTransition, SessionManager, VState


@dataclass
class _BehaviorTrackers:
    guild_id: int
    join_times: list
    new_account_joins: list
    verification_times: list
    user_messages: dict
    user_mentions: dict
    roblox_attempts: dict
    network_verifs: dict
    role_adds: dict


class BehaviorTracker:
    def __init__(self) -> None:
        self._guilds: dict = {}

    def _g(self, guild_id: int) -> _BehaviorTrackers:
        g = self._guilds.get(guild_id)
        if g is None:
            g = _BehaviorTrackers(guild_id, [], [], [], {}, {}, {}, {}, {})
            self._guilds[guild_id] = g
        return g

    def record_join(self, guild_id: int, account_age_days: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        g.join_times.append(now)
        g.join_times[:] = [t for t in g.join_times if t > now - 600]
        if account_age_days < 7:
            g.new_account_joins.append(now)
            g.new_account_joins[:] = [t for t in g.new_account_joins if t > now - 600]

    def record_verification(self, guild_id: int) -> None:
        g = self._g(guild_id)
        now = time.monotonic()
        g.verification_times.append(now)
        g.verification_times[:] = [t for t in g.verification_times if t > now - 300]

    def record_message(self, guild_id: int, user_id: int, mention_ids: set) -> None:
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

    def snapshot(self, guild_id: int, user_id: int) -> dict:
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


async def _run_one(det, ctx, timeout=6.0):
    try:
        return await asyncio.wait_for(det.evaluate(ctx), timeout=timeout)
    except asyncio.TimeoutError:
        return DResult(det.id, DStatus.ERROR, False, 0.0, 0.0, 0.0,
                       det.evidence_type, det.family, "detector timeout")
    except Exception as exc:
        return det._error(exc)


async def run_detectors(registry: DetectorRegistry, ctx: DetectorContext,
                        timeout: float = 8.0, max_concurrency: int = 12) -> list:
    sem = asyncio.Semaphore(max_concurrency)
    async def wrapped(d):
        async with sem:
            return await _run_one(d, ctx)
    return await asyncio.gather(*(wrapped(d) for d in registry.all()))


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

        self._cluster_fingerprint_index: dict = {}
        self._cluster_fingerprint_rarity: dict = {}

    # ---- behavior hooks ----
    def on_member_join(self, member: discord.Member, account_age_days: int) -> None:
        self.behavior.record_join(member.guild.id, account_age_days)

    def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        mention_ids = {m.id for m in message.mentions}
        self.behavior.record_message(message.guild.id, message.author.id, mention_ids)

    def on_role_add(self, guild_id: int, user_id: int) -> None:
        self.behavior.record_role_add(guild_id, user_id)

    # ---- boot-time rebuild ----
    async def rebuild_fingerprint_index(self, guild_id: int) -> None:
        avatars = await self.repo.all_avatar_hashes(guild_id)
        names = await self.repo.all_name_hashes(guild_id)
        for uid, h in avatars:
            self._cluster_fingerprint_index.setdefault("avatar:" + h, set()).add(uid)
        for uid, h in names:
            self._cluster_fingerprint_index.setdefault("name_norm:" + h, set()).add(uid)
        for fp, ids in self._cluster_fingerprint_index.items():
            self._cluster_fingerprint_rarity[fp] = 1.0 / max(len(ids), 1)

    # ---- events ----
    async def on_member_leave(self, member: discord.Member) -> None:
        try:
            await self.repo.record_attempt(member.guild.id, member.id, "n/a", "LEFT", 0)
        except Exception:
            pass

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        try:
            username = user.name
            display_name = getattr(user, "display_name", user.name)
            avatar_url = str(user.display_avatar.url) if user.display_avatar else ""
            avatar_hash = hashlib.sha256(avatar_url.encode("utf-8")).hexdigest()[:32] if avatar_url else ""
            name_hash = hashlib.sha256((username or "").lower().encode("utf-8")).hexdigest()[:16] if username else ""
            await self.repo.record_ban(guild.id, user.id, username, display_name, avatar_hash, name_hash, "")
        except Exception:
            pass

    async def record_rejoin_if_applicable(self, member: discord.Member) -> None:
        try:
            recent_left = await self.repo.count_recent_outcome(member.guild.id, member.id, "LEFT", 86400)
            if recent_left >= 1:
                await self.repo.record_attempt(member.guild.id, member.id, "n/a", "REJOIN", 0)
        except Exception:
            pass

    async def save_member_history(self, member: discord.Member) -> None:
        try:
            await self.repo.set_history(member.guild.id, member.id, "username", member.name or "")
            await self.repo.set_history(member.guild.id, member.id, "display_name", member.display_name or "")
            url = str(member.display_avatar.url) if member.display_avatar else ""
            if url:
                h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
                await self.repo.set_history(member.guild.id, member.id, "avatar_hash", h)
            if member.name:
                nh = hashlib.sha256(member.name.lower().encode("utf-8")).hexdigest()[:16]
                await self.repo.set_history(member.guild.id, member.id, "name_hash", nh)
        except Exception:
            pass

    # ---- main assess ----
    async def assess(self, member: discord.Member, session_id: str,
                     session_started: float) -> RiskVerdict:
        guild_id = member.guild.id
        user_id = member.id
        now = datetime.now(timezone.utc)
        account_age_days = max((now - member.created_at).days, 0)
        join_age = 0
        if member.joined_at:
            join_age = int((now - member.joined_at).total_seconds())

        history = await self._build_history(member)

        roblox = None
        roblox_id = None
        link = await self.repo.get_roblox_link(guild_id, user_id)
        if link:
            roblox_id = int(link["roblox_id"])
            try:
                roblox = await asyncio.wait_for(
                    self.roblox_provider.lookup_user_by_id(roblox_id), timeout=5.0,
                )
            except Exception:
                roblox = None

        network = None
        network_id = None
        try:
            network = await asyncio.wait_for(self.network_provider.lookup(None), timeout=3.0)
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

        cluster = ClusterEngine.cluster_for(user_id, self._cluster_fingerprint_index,
                                             self._cluster_fingerprint_rarity)
        history["cluster"] = {"size": len(cluster.member_ids), "confidence": cluster.confidence}

        base_ctx = DetectorContext(
            guild=member.guild, member=member, session_id=session_id,
            session_started_at=session_started, account_age_days=account_age_days,
            join_age_seconds=join_age, roblox=roblox, roblox_id=roblox_id,
            network=network, network_id=network_id, history=history,
            behavior=self._behavior_snapshot(guild_id, user_id, network_id),
        )

        results_first = await run_detectors(self.registry, base_ctx)
        triggered_fams = {r.signal_family for r in results_first
                          if r.status == DStatus.TRIGGERED and r.triggered}
        base_ctx.extras["triggered_families"] = triggered_fams
        cross = self.registry.get("CROSS_SIGNAL_CORRELATION")
        if cross is not None:
            replacement = await _run_one(cross, base_ctx)
            results_first = [r for r in results_first if r.detector != cross.id]
            results_first.append(replacement)

        verdict = self.risk.evaluate(results_first)
        verdict.assessment_id = await self.repo.save_assessment(guild_id, user_id, session_id, verdict)

        await self._update_clusters(guild_id, member, verdict)
        return verdict

    async def _build_history(self, member: discord.Member) -> dict:
        gid = member.guild.id
        uid = member.id
        hist: dict = {}
        hist["last_username"] = await self.repo.get_history(gid, uid, "username")
        hist["last_display_name"] = await self.repo.get_history(gid, uid, "display_name")

        avatar_url = str(member.display_avatar.url) if member.display_avatar else ""
        avatar_hash = hashlib.sha256(avatar_url.encode("utf-8")).hexdigest()[:32] if avatar_url else ""
        if avatar_hash:
            hist["avatar_seen_users"] = await self.repo.avatar_hash_seen_users(gid, avatar_hash, uid)

        hist["user_recent_failures"] = await self.repo.count_recent_failures(gid, uid, 3600)
        hist["user_rejoin_count_24h"] = await self.repo.count_recent_outcome(gid, uid, "REJOIN", 86400)
        hist["user_leave_count_30d"] = await self.repo.count_recent_outcome(gid, uid, "LEFT", 30 * 86400)
        hist["user_prior_quarantines"] = await self.repo.count_user_quarantines(gid, uid)
        hist["user_roblox_failures"] = await self.repo.count_recent_outcome(gid, uid, "ROBLOX_FAIL", 86400)
        hist["user_roblox_link_count"] = await self.repo.roblox_links_for_user(gid, uid)

        if member and member.id:
            link = await self.repo.get_roblox_link(gid, uid)
            if link:
                rbx = int(link["roblox_id"])
                hist["roblox_link_prior_users"] = await self.repo.roblox_link_prior_users(gid, rbx, uid)
                hist["roblox_cluster_size"] = await self.repo.roblox_cluster_size(gid, rbx)

        name_hash = hashlib.sha256((member.name or "").lower().encode("utf-8")).hexdigest()[:16] if member.name else ""
        hist["ban_evasion_matches"] = await self.repo.ban_hash_matches(gid, avatar_hash, name_hash)

        sig_values = {
            "avatar_hash": avatar_hash,
            "name_hash": name_hash,
            "username": (member.name or "").lower(),
        }
        hist["known_abuse_signature_matches"] = await self.repo.match_signatures(gid, sig_values)

        hist["member_fingerprints"] = {
            "avatar": avatar_hash,
            "name": name_hash,
        }
        hist["known_bad_signals"] = {}
        hist["user_recent_role_adds"] = self.behavior.user_role_adds_last_1h(gid, uid)
        return hist

    def _behavior_snapshot(self, guild_id: int, user_id: int, network_id: Optional[str]) -> dict:
        snap = self.behavior.snapshot(guild_id, user_id)
        if network_id:
            snap["network_verifications_last_10m"] = self.behavior.network_verifications_last_10m(guild_id, network_id)
        return snap

    async def _update_clusters(self, guild_id: int, member: discord.Member, verdict: RiskVerdict) -> None:
        fps: set = set()
        url = str(member.display_avatar.url) if member.display_avatar else ""
        if url:
            fps.add("avatar:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32])
        if member.name:
            fps.add("name_norm:" + hashlib.sha256(member.name.lower().encode("utf-8")).hexdigest()[:16])
        for fp in fps:
            ids = self._cluster_fingerprint_index.setdefault(fp, set())
            ids.add(member.id)
            self._cluster_fingerprint_rarity[fp] = 1.0 / max(len(ids), 1)

    # ---- public API ----
    async def create_session(self, guild_id: int, user_id: int):
        try:
            await self.rate.hit("session:g" + str(guild_id), limit=60, window_seconds=60)
            await self.rate.hit("session:u" + str(guild_id) + ":" + str(user_id), limit=5, window_seconds=60)
        except RateLimitExceeded:
            return None
        return await self.sessions.create(guild_id, user_id)

    async def verify(self, guild_id: int, user_id: int, session_id: str) -> RiskVerdict:
        await self.rate.hit("verify:g" + str(guild_id), limit=100, window_seconds=60)
        await self.rate.hit("verify:u" + str(guild_id) + ":" + str(user_id), limit=10, window_seconds=300)
        await self.rate.hit("attempt:u" + str(guild_id) + ":" + str(user_id), limit=20, window_seconds=3600)

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
                                  "layer=" + str(sess.layer) + " risk=" + str(sess.risk_score) +
                                  " conf=" + format(sess.confidence, ".2f"))
        return verdict

    async def link_roblox(self, guild_id: int, user_id: int, username: str):
        await self.rate.hit("roblox_link:u" + str(guild_id) + ":" + str(user_id), limit=5, window_seconds=3600)
        self.behavior.record_roblox_attempt(guild_id, user_id)

        profile = await self.roblox_provider.lookup_user_by_username(username)
        if not profile.available or not profile.user_id:
            await self.repo.record_attempt(guild_id, user_id, "n/a", "ROBLOX_FAIL", 0)
            return None
        await self.repo.save_roblox_link(guild_id, user_id, profile.user_id,
                                         profile.username or username)
        return profile
