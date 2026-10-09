"""The 49 active detectors. Every detector implements the same contract.

A detector NEVER decides the verdict. It produces evidence; the RiskEngine decides.
UNKNOWN / UNAVAILABLE / ERROR never increase risk.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import discord

from bot.verification.providers import NetworkVerdict, RobloxProfile
from bot.verification.redaction import rex


class DStatus(str, Enum):
    TRIGGERED = "TRIGGERED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class Family(str, Enum):
    DISCORD = "DISCORD"
    BEHAVIOR = "BEHAVIOR"
    ROBLOX = "ROBLOX"
    NETWORK = "NETWORK"
    DEVICE = "DEVICE"
    BROWSER = "BROWSER"
    HISTORICAL = "HISTORICAL"
    CORRELATION = "CORRELATION"


@dataclass
class DResult:
    detector: str
    status: DStatus
    triggered: bool
    severity: float
    confidence: float
    score_contribution: float
    evidence_type: str
    signal_family: Family
    safe_reason: str
    weight: float = 1.0


@dataclass
class DetectorContext:
    guild: discord.Guild
    member: discord.Member
    session_id: str
    session_started_at: float
    account_age_days: int
    join_age_seconds: int
    roblox: Optional[RobloxProfile] = None
    roblox_id: Optional[int] = None
    network: Optional[NetworkVerdict] = None
    network_id: Optional[str] = None
    history: dict[str, Any] = field(default_factory=dict)
    behavior: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


class Detector:
    id: str = "BASE"
    family: Family = Family.DISCORD
    description: str = ""
    default_weight: float = 1.0
    evidence_type: str = "generic"

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        raise NotImplementedError

    def _ok(self, triggered: bool, severity: float, confidence: float, reason: str) -> DResult:
        return DResult(
            detector=self.id,
            status=DStatus.TRIGGERED if triggered else DStatus.NOT_TRIGGERED,
            triggered=triggered,
            severity=severity if triggered else 0.0,
            confidence=confidence,
            score_contribution=severity * confidence * self.default_weight if triggered else 0.0,
            evidence_type=self.evidence_type,
            signal_family=self.family,
            safe_reason=reason,
            weight=self.default_weight,
        )

    def _unavailable(self, reason: str) -> DResult:
        return DResult(
            self.id, DStatus.UNAVAILABLE, False, 0.0, 0.0, 0.0,
            self.evidence_type, self.family, reason, self.default_weight,
        )

    def _unknown(self, reason: str) -> DResult:
        return DResult(
            self.id, DStatus.UNKNOWN, False, 0.0, 0.0, 0.0,
            self.evidence_type, self.family, reason, self.default_weight,
        )

    def _error(self, exc: BaseException) -> DResult:
        return DResult(
            self.id, DStatus.ERROR, False, 0.0, 0.0, 0.0,
            self.evidence_type, self.family,
            "internal error: " + rex(exc)[:120], self.default_weight,
        )


# ---------------------------------------------------------------------------
# DISCORD (1-10)
# ---------------------------------------------------------------------------
class D01AccountAge(Detector):
    id = "DISCORD_ACCOUNT_AGE"
    family = Family.DISCORD
    evidence_type = "account_age"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        days = ctx.account_age_days
        if days < 1:
            return self._ok(True, 0.85, 0.98, "Discord account younger than 1 day")
        if days < 7:
            return self._ok(True, 0.55, 0.95, "Discord account younger than 7 days")
        if days < 30:
            return self._ok(True, 0.30, 0.90, "Discord account younger than 30 days")
        if days < 90:
            return self._ok(True, 0.12, 0.85, "Discord account younger than 90 days")
        return self._ok(False, 0.0, 0.9, "Discord account age within normal range")


class D02UnusuallyNew(Detector):
    id = "DISCORD_ACCOUNT_UNUSUALLY_NEW"
    family = Family.DISCORD
    evidence_type = "account_age_extreme"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.account_age_days < 1:
            return self._ok(True, 0.95, 0.99, "Discord account is less than 24 hours old")
        if ctx.account_age_days < 3:
            return self._ok(True, 0.70, 0.95, "Discord account is less than 3 days old")
        return self._ok(False, 0.0, 0.9, "Account age not unusual")


class D03ServerJoinAge(Detector):
    id = "SERVER_JOIN_AGE"
    family = Family.DISCORD
    evidence_type = "join_age"
    default_weight = 0.8

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        secs = ctx.join_age_seconds
        if secs < 60:
            return self._ok(True, 0.55, 0.95, "Joined this server less than a minute ago")
        if secs < 600:
            return self._ok(True, 0.30, 0.90, "Joined this server less than 10 minutes ago")
        if secs < 3600:
            return self._ok(True, 0.15, 0.85, "Joined this server less than an hour ago")
        return self._ok(False, 0.0, 0.9, "Not a fresh join")


class D04RecentUsernameChange(Detector):
    id = "RECENT_USERNAME_CHANGE"
    family = Family.DISCORD
    evidence_type = "identity_change"
    default_weight = 1.1

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        last = ctx.history.get("last_username")
        if not last:
            return self._unknown("No prior username on record for this account")
        if str(last) != ctx.member.name:
            return self._ok(True, 0.35, 0.85, "Username changed since last seen")
        return self._ok(False, 0.0, 0.9, "Username unchanged since last seen")


class D05RecentDisplayNameChange(Detector):
    id = "RECENT_DISPLAY_NAME_CHANGE"
    family = Family.DISCORD
    evidence_type = "identity_change"
    default_weight = 0.6

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        last = ctx.history.get("last_display_name")
        if not last:
            return self._unknown("No prior display name on record")
        if str(last) != (ctx.member.display_name or ""):
            return self._ok(True, 0.20, 0.80, "Display name changed since last seen")
        return self._ok(False, 0.0, 0.85, "Display name unchanged")


class D06AvatarReuse(Detector):
    id = "AVATAR_REUSE"
    family = Family.DISCORD
    evidence_type = "avatar_collision"
    default_weight = 1.3

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        url = str(ctx.member.display_avatar.url) if ctx.member.display_avatar else ""
        if not url:
            return self._unknown("No avatar URL available")
        fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        seen = ctx.history.get("avatar_seen_users") or []
        other_users = [u for u in seen if int(u) != ctx.member.id]
        if other_users:
            return self._ok(True, 0.60, 0.80, "Same avatar asset observed on other accounts")
        return self._ok(False, 0.0, 0.85, "Avatar not previously seen on other accounts")


class D07LowProfileActivity(Detector):
    id = "LOW_PROFILE_ACTIVITY"
    family = Family.DISCORD
    evidence_type = "profile_activity"

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        return self._unavailable("Discord does not expose profile activity to bots")


class D08MutualServerPattern(Detector):
    id = "MUTUAL_SERVER_PATTERN"
    family = Family.DISCORD
    evidence_type = "mutual_guilds"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        try:
            mutuals = list(ctx.member.mutual_guilds) if ctx.member.mutual_guilds else []
        except Exception:
            return self._unknown("Mutual guilds not available")
        if not mutuals:
            return self._unavailable("No mutual servers known to this bot")
        bot_in = [g for g in mutuals if g.me in g.members]
        if len(bot_in) >= 3:
            return self._ok(True, 0.30, 0.55, "Shares " + str(len(bot_in)) + " mutual servers with this bot")
        return self._ok(False, 0.0, 0.6, "Mutual server pattern unremarkable")


class D09KnownBadAccountCorrelation(Detector):
    id = "KNOWN_BAD_ACCOUNT_CORRELATION"
    family = Family.DISCORD
    evidence_type = "prior_bad_account"
    default_weight = 1.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        fingerprints = ctx.history.get("member_fingerprints") or {}
        signals = ctx.history.get("known_bad_signals") or {}
        hits = 0
        for key, value in fingerprints.items():
            if signals.get(key) == value:
                hits += 1
        if hits >= 2:
            return self._ok(True, 0.75, 0.70,
                            "Matches " + str(hits) + " fingerprint(s) of previously actioned accounts")
        if hits == 1:
            return self._ok(True, 0.35, 0.60, "Matches 1 fingerprint of a previously actioned account")
        return self._ok(False, 0.0, 0.7, "No correlation with previously actioned accounts")


class D10AccountClusterPattern(Detector):
    id = "ACCOUNT_CLUSTER_PATTERN"
    family = Family.DISCORD
    evidence_type = "cluster"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        cluster = ctx.history.get("cluster") or {}
        size = int(cluster.get("size", 0))
        conf = float(cluster.get("confidence", 0.0))
        if size >= 4 and conf >= 0.6:
            return self._ok(True, 0.65, conf, "Part of a cluster of " + str(size) + " correlated accounts")
        if size >= 2 and conf >= 0.5:
            return self._ok(True, 0.35, conf, "Part of a cluster of " + str(size) + " accounts")
        return self._ok(False, 0.0, 0.6, "No account cluster detected")


# ---------------------------------------------------------------------------
# BEHAVIOR (11-20)
# ---------------------------------------------------------------------------
class D11JoinBurst(Detector):
    id = "JOIN_BURST"
    family = Family.BEHAVIOR
    evidence_type = "join_velocity"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        count = int(ctx.behavior.get("guild_joins_last_60s", 0))
        if count >= 15:
            return self._ok(True, 0.75, 0.9, str(count) + " joins in the last minute")
        if count >= 8:
            return self._ok(True, 0.45, 0.85, str(count) + " joins in the last minute")
        if count >= 5:
            return self._ok(True, 0.20, 0.8, str(count) + " joins in the last minute")
        return self._ok(False, 0.0, 0.85, "No join burst")


class D12VerificationBurst(Detector):
    id = "VERIFICATION_BURST"
    family = Family.BEHAVIOR
    evidence_type = "verification_velocity"
    default_weight = 1.3

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        count = int(ctx.behavior.get("guild_verifications_last_120s", 0))
        if count >= 10:
            return self._ok(True, 0.70, 0.9, str(count) + " verifications in the last 2 minutes")
        if count >= 5:
            return self._ok(True, 0.40, 0.85, str(count) + " verifications in the last 2 minutes")
        return self._ok(False, 0.0, 0.8, "No verification burst")


class D13RepeatedVerificationFailure(Detector):
    id = "REPEATED_VERIFICATION_FAILURE"
    family = Family.BEHAVIOR
    evidence_type = "verification_failures"
    default_weight = 1.1

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        fails = int(ctx.history.get("user_recent_failures", 0))
        if fails >= 5:
            return self._ok(True, 0.55, 0.85, str(fails) + " recent verification failures for this account")
        if fails >= 3:
            return self._ok(True, 0.30, 0.80, str(fails) + " recent verification failures for this account")
        return self._ok(False, 0.0, 0.85, "No repeated failures")


# ---------------------------------------------------------------------------
# D14 REMOVED FROM REGISTRY - semantically broken in this architecture.
# The class is retained below for reference only. Do not register it.
# ---------------------------------------------------------------------------
class D14UnusualVerificationSpeed(Detector):
    id = "UNUSUAL_VERIFICATION_SPEED"
    family = Family.BEHAVIOR
    evidence_type = "verification_timing"
    default_weight = 0.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        return self._unavailable("Disabled: not meaningful in interaction-based verification flow")


class D15UnusualVerificationDelay(Detector):
    id = "UNUSUAL_VERIFICATION_DELAY"
    family = Family.BEHAVIOR
    evidence_type = "verification_timing"
    default_weight = 0.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        elapsed = time.monotonic() - ctx.session_started_at
        if elapsed > 3600:
            return self._ok(True, 0.15, 0.7, "Very long delay between session start and completion")
        return self._ok(False, 0.0, 0.75, "Timing normal")


class D16NewAccountJoinWave(Detector):
    id = "NEW_ACCOUNT_JOIN_WAVE"
    family = Family.BEHAVIOR
    evidence_type = "new_account_wave"
    default_weight = 1.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        new_accounts = int(ctx.behavior.get("guild_new_account_joins_last_300s", 0))
        if new_accounts >= 6:
            return self._ok(True, 0.70, 0.85,
                            str(new_accounts) + " accounts younger than 7 days joined recently")
        if new_accounts >= 3:
            return self._ok(True, 0.35, 0.80,
                            str(new_accounts) + " accounts younger than 7 days joined recently")
        return self._ok(False, 0.0, 0.8, "No wave of new-account joins")


class D17PostJoinBehavior(Detector):
    id = "POST_JOIN_BEHAVIOR"
    family = Family.BEHAVIOR
    evidence_type = "behavior"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        msgs = int(ctx.behavior.get("user_messages_first_10m", 0))
        mentions = int(ctx.behavior.get("user_unique_mentions_first_10m", 0))
        if mentions >= 8:
            return self._ok(True, 0.45, 0.75,
                            "Mentioned " + str(mentions) + " distinct members within first 10 minutes")
        if msgs >= 30:
            return self._ok(True, 0.30, 0.7, "Sent " + str(msgs) + " messages within first 10 minutes")
        return self._ok(False, 0.0, 0.75, "Post-join behavior normal")


class D18RoleEscalationPattern(Detector):
    id = "ROLE_ESCALATION_PATTERN"
    family = Family.BEHAVIOR
    evidence_type = "role_escalation"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        escalations = int(ctx.history.get("user_recent_role_adds", 0))
        if escalations >= 4:
            return self._ok(True, 0.45, 0.7,
                            str(escalations) + " role additions recorded in the last hour")
        return self._ok(False, 0.0, 0.75, "No role escalation pattern")


class D19RejoinPattern(Detector):
    id = "REJOIN_PATTERN"
    family = Family.BEHAVIOR
    evidence_type = "rejoin"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        rejoins = int(ctx.history.get("user_rejoin_count_24h", 0))
        if rejoins >= 3:
            return self._ok(True, 0.55, 0.85, "Rejoined " + str(rejoins) + " times in the last 24 hours")
        if rejoins >= 2:
            return self._ok(True, 0.30, 0.80, "Rejoined " + str(rejoins) + " times in the last 24 hours")
        return self._ok(False, 0.0, 0.85, "No recent rejoins")


class D20BanEvasionPattern(Detector):
    id = "BAN_EVASION_PATTERN"
    family = Family.BEHAVIOR
    evidence_type = "ban_evasion"
    default_weight = 1.6

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        matches = int(ctx.history.get("ban_evasion_matches", 0))
        if matches >= 2:
            return self._ok(True, 0.85, 0.75,
                            "Matches " + str(matches) + " signals recorded on a previously banned account")
        if matches == 1:
            return self._ok(True, 0.40, 0.60, "Matches 1 signal on a previously banned account")
        return self._ok(False, 0.0, 0.7, "No ban evasion signals matched")


# ---------------------------------------------------------------------------
# ROBLOX (21-28)
# ---------------------------------------------------------------------------
class D21RobloxAccountAge(Detector):
    id = "ROBLOX_ACCOUNT_AGE"
    family = Family.ROBLOX
    evidence_type = "roblox_age"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        rp = ctx.roblox
        if rp is None or not rp.available or rp.account_age_days is None:
            return self._unavailable("Roblox profile unavailable")
        d = rp.account_age_days
        if d < 1:
            return self._ok(True, 0.75, 0.85, "Roblox account younger than 1 day")
        if d < 7:
            return self._ok(True, 0.45, 0.85, "Roblox account younger than 7 days")
        if d < 30:
            return self._ok(True, 0.20, 0.8, "Roblox account younger than 30 days")
        return self._ok(False, 0.0, 0.85, "Roblox account age normal")


class D22RobloxActivityLevel(Detector):
    id = "ROBLOX_ACTIVITY_LEVEL"
    family = Family.ROBLOX
    evidence_type = "roblox_activity"
    default_weight = 0.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        rp = ctx.roblox
        if rp is None or not rp.available or rp.friend_count is None:
            return self._unavailable("Roblox activity data unavailable")
        if rp.friend_count == 0 and (rp.account_age_days or 0) > 180:
            return self._ok(True, 0.20, 0.55, "Long-lived Roblox account with zero friends")
        return self._ok(False, 0.0, 0.6, "Roblox activity level unremarkable")


class D23RobloxAccountReuse(Detector):
    id = "ROBLOX_ACCOUNT_REUSE"
    family = Family.ROBLOX
    evidence_type = "roblox_reuse"
    default_weight = 1.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if not ctx.roblox_id:
            return self._unavailable("No Roblox account linked yet")
        prior = int(ctx.history.get("roblox_link_prior_users", 0))
        if prior >= 2:
            return self._ok(True, 0.80, 0.85,
                            "Roblox account previously linked to " + str(prior) + " other Discord accounts")
        if prior == 1:
            return self._ok(True, 0.45, 0.75,
                            "Roblox account previously linked to another Discord account")
        return self._ok(False, 0.0, 0.8, "Roblox account not previously linked")


class D24RobloxDiscordLinkHistory(Detector):
    id = "ROBLOX_DISCORD_LINK_HISTORY"
    family = Family.ROBLOX
    evidence_type = "roblox_history"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        total = int(ctx.history.get("user_roblox_link_count", 0))
        if total >= 4:
            return self._ok(True, 0.45, 0.75,
                            "This Discord account has linked " + str(total) + " distinct Roblox accounts")
        if total >= 2:
            return self._ok(True, 0.20, 0.70,
                            "This Discord account has linked " + str(total) + " distinct Roblox accounts")
        return self._ok(False, 0.0, 0.75, "Link history normal")


class D25RobloxProfileAnomaly(Detector):
    id = "ROBLOX_PROFILE_ANOMALY"
    family = Family.ROBLOX
    evidence_type = "roblox_anomaly"
    default_weight = 0.7

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        rp = ctx.roblox
        if rp is None or not rp.available:
            return self._unavailable("Roblox profile unavailable")
        age = rp.account_age_days or 0
        no_desc = (rp.description_length or 0) == 0
        no_friends = (rp.friend_count or 0) == 0
        if age < 30 and no_desc and no_friends:
            return self._ok(True, 0.30, 0.65, "Recent Roblox account with no bio and no friends")
        return self._ok(False, 0.0, 0.7, "Profile looks normal")


class D26RobloxVerificationFailures(Detector):
    id = "ROBLOX_VERIFICATION_FAILURES"
    family = Family.ROBLOX
    evidence_type = "roblox_failures"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        fails = int(ctx.history.get("user_roblox_failures", 0))
        if fails >= 4:
            return self._ok(True, 0.40, 0.75,
                            str(fails) + " failed Roblox verification attempts recently")
        if fails >= 2:
            return self._ok(True, 0.20, 0.7,
                            str(fails) + " failed Roblox verification attempts recently")
        return self._ok(False, 0.0, 0.75, "No recent Roblox failures")


class D27RobloxLinkBurst(Detector):
    id = "ROBLOX_LINK_BURST"
    family = Family.ROBLOX
    evidence_type = "roblox_link_burst"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        attempts = int(ctx.behavior.get("user_roblox_attempts_last_5m", 0))
        if attempts >= 5:
            return self._ok(True, 0.45, 0.8,
                            str(attempts) + " Roblox link attempts in 5 minutes")
        if attempts >= 3:
            return self._ok(True, 0.20, 0.75,
                            str(attempts) + " Roblox link attempts in 5 minutes")
        return self._ok(False, 0.0, 0.8, "No link burst")


class D28RobloxClusterCorrelation(Detector):
    id = "ROBLOX_CLUSTER_CORRELATION"
    family = Family.ROBLOX
    evidence_type = "roblox_cluster"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if not ctx.roblox_id:
            return self._unavailable("No Roblox account linked yet")
        count = int(ctx.history.get("roblox_cluster_size", 0))
        if count >= 3:
            return self._ok(True, 0.55, 0.7,
                            "Roblox account is linked to a cluster of " + str(count) + " accounts")
        return self._ok(False, 0.0, 0.7, "No Roblox cluster")


# ---------------------------------------------------------------------------
# NETWORK (29-36) - UNAVAILABLE by default (no IP collection)
# ---------------------------------------------------------------------------
class _NetBase(Detector):
    family = Family.NETWORK

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        nv = ctx.network
        if nv is None or not nv.available:
            return self._unavailable("Network provider not configured")
        return self._ok(False, 0.0, 0.75, "Network provider returned no signal")


class D29Vpn(_NetBase):
    id = "VPN_DETECTED"
    evidence_type = "vpn"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if ctx.network.vpn:
            return self._ok(True, 0.45, 0.75,
                            "VPN infrastructure observed on the verification path")
        return self._ok(False, 0.0, 0.75, "No VPN indicator")


class D30Proxy(_NetBase):
    id = "PROXY_DETECTED"
    evidence_type = "proxy"
    default_weight = 1.1

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if ctx.network.proxy:
            return self._ok(True, 0.40, 0.70,
                            "Proxy infrastructure observed on the verification path")
        return self._ok(False, 0.0, 0.70, "No proxy indicator")


class D31Datacenter(_NetBase):
    id = "DATACENTER_ASN"
    evidence_type = "datacenter"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if ctx.network.datacenter:
            return self._ok(True, 0.35, 0.75,
                            "Datacenter network on the verification path")
        return self._ok(False, 0.0, 0.75, "Not a datacenter network")


class D32IpReputation(_NetBase):
    id = "IP_REPUTATION"
    evidence_type = "reputation"
    default_weight = 1.3

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        rep = ctx.network.reputation
        if rep is None:
            return self._unavailable("Reputation data unavailable from provider")
        if rep >= 0.8:
            return self._ok(True, 0.65, 0.70, "Network reputation reported as abusive")
        if rep >= 0.5:
            return self._ok(True, 0.35, 0.65, "Network reputation reported as suspicious")
        return self._ok(False, 0.0, 0.7, "Network reputation clean")


class D33Tor(_NetBase):
    id = "TOR_DETECTED"
    evidence_type = "tor"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if ctx.network.tor:
            return self._ok(True, 0.55, 0.80, "Tor exit node on the verification path")
        return self._ok(False, 0.0, 0.80, "No Tor indicator")


class D34NetworkRiskScore(_NetBase):
    id = "NETWORK_RISK_SCORE"
    evidence_type = "network_risk"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        score = ctx.network.risk_score
        if score is None:
            return self._unavailable("Provider did not return a composite risk score")
        if score >= 0.75:
            return self._ok(True, 0.55, 0.70, "Provider reported high composite network risk")
        if score >= 0.45:
            return self._ok(True, 0.25, 0.65, "Provider reported elevated composite network risk")
        return self._ok(False, 0.0, 0.7, "Composite network risk within normal bounds")


class D35IpVerificationVelocity(_NetBase):
    id = "IP_VERIFICATION_VELOCITY"
    evidence_type = "network_velocity"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if not ctx.network_id:
            return self._unavailable("No pseudonymous network identifier available")
        count = int(ctx.behavior.get("network_verifications_last_10m", 0))
        if count >= 8:
            return self._ok(True, 0.75, 0.70,
                            str(count) + " verifications from the same network path in 10 minutes")
        if count >= 4:
            return self._ok(True, 0.40, 0.65,
                            str(count) + " verifications from the same network path in 10 minutes")
        return self._ok(False, 0.0, 0.7, "Verification velocity from this network normal")


class D36InfrastructureCluster(_NetBase):
    id = "INFRASTRUCTURE_CLUSTER"
    evidence_type = "infra_cluster"
    default_weight = 1.2

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.network is None or not ctx.network.available:
            return self._unavailable("Network provider not configured")
        if not ctx.network_id:
            return self._unavailable("No pseudonymous network identifier available")
        users = int(ctx.history.get("network_distinct_users", 0))
        if users >= 5:
            return self._ok(True, 0.60, 0.65,
                            "Network path used by " + str(users) + " distinct accounts recently")
        if users >= 3:
            return self._ok(True, 0.30, 0.60,
                            "Network path used by " + str(users) + " distinct accounts recently")
        return self._ok(False, 0.0, 0.65, "Infrastructure shared with few accounts")


# ---------------------------------------------------------------------------
# HISTORICAL / CORRELATION (37-40)
# ---------------------------------------------------------------------------
class D37PreviousServerHistory(Detector):
    id = "PREVIOUS_SERVER_HISTORY"
    family = Family.HISTORICAL
    evidence_type = "server_history"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        left_count = int(ctx.history.get("user_leave_count_30d", 0))
        if left_count >= 4:
            return self._ok(True, 0.35, 0.75,
                            "Left this server " + str(left_count) + " times in the last 30 days")
        return self._ok(False, 0.0, 0.8, "Server history unremarkable")


class D38PreviousVerificationHistory(Detector):
    id = "PREVIOUS_VERIFICATION_HISTORY"
    family = Family.HISTORICAL
    evidence_type = "verif_history"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        prior = int(ctx.history.get("user_prior_quarantines", 0))
        if prior >= 1:
            return self._ok(True, 0.55, 0.75,
                            "This account has been quarantined " + str(prior) + " time(s) previously")
        return self._ok(False, 0.0, 0.8, "No prior quarantine history")


class D39CrossSignalCorrelation(Detector):
    id = "CROSS_SIGNAL_CORRELATION"
    family = Family.CORRELATION
    evidence_type = "cross_family"
    default_weight = 1.3

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        families = ctx.extras.get("triggered_families") or set()
        count = len(families)
        if count >= 4:
            return self._ok(True, 0.80, 0.75,
                            str(count) + " independent signal families triggered together")
        if count >= 3:
            return self._ok(True, 0.55, 0.70,
                            str(count) + " independent signal families triggered together")
        if count >= 2:
            return self._ok(True, 0.25, 0.65,
                            str(count) + " independent signal families triggered together")
        return self._ok(False, 0.0, 0.7, "No cross-family correlation")


class D40KnownAbusePattern(Detector):
    id = "KNOWN_ABUSE_PATTERN"
    family = Family.HISTORICAL
    evidence_type = "known_abuse"
    default_weight = 1.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        matches = int(ctx.history.get("known_abuse_signature_matches", 0))
        if matches >= 3:
            return self._ok(True, 0.85, 0.80,
                            "Matches " + str(matches) + " attributes of a known-abuse signature")
        if matches >= 2:
            return self._ok(True, 0.45, 0.65,
                            "Matches " + str(matches) + " attributes of a known-abuse signature")
        return self._ok(False, 0.0, 0.75, "No known abuse pattern match")


# ---------------------------------------------------------------------------
# EXTENDED SIGNALS (41-45) - Discord-native, no IP required
# ---------------------------------------------------------------------------
class D41PublicFlags(Detector):
    """Trust signal: Discord public badges. Early Supporter is impossible to fake."""
    id = "DISCORD_PUBLIC_FLAGS"
    family = Family.DISCORD
    evidence_type = "public_flags"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        flags = getattr(ctx.member, "public_flags", None)
        if flags is None:
            return self._unavailable("Public flags unavailable")

        strong = []
        if getattr(flags, "early_supporter", False):
            strong.append("Early Supporter")
        if getattr(flags, "active_developer", False):
            strong.append("Active Developer")
        if getattr(flags, "verified_developer", False) or getattr(flags, "early_verified_bot_developer", False):
            strong.append("Verified Developer")
        if getattr(flags, "discord_certified_moderator", False):
            strong.append("Certified Moderator")
        if getattr(flags, "staff", False):
            strong.append("Discord Staff")
        if getattr(flags, "partner", False):
            strong.append("Partner")
        if getattr(flags, "bug_hunter_level_2", False) or getattr(flags, "bug_hunter", False):
            strong.append("Bug Hunter")

        if strong:
            label = "Verified signal(s): " + ", ".join(strong)
            return DResult(
                detector=self.id,
                status=DStatus.TRIGGERED,
                triggered=True,
                severity=-0.55,
                confidence=0.95,
                score_contribution=-0.55 * 0.95,
                evidence_type=self.evidence_type,
                signal_family=self.family,
                safe_reason=label,
                weight=self.default_weight,
            )
        return self._ok(False, 0.0, 0.7, "No trust badges on this account")


class D42SnowflakePrecision(Detector):
    """Hour-precise account age."""
    id = "SNOWFLAKE_PRECISION"
    family = Family.DISCORD
    evidence_type = "account_age_hours"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        created = ctx.member.created_at
        if created is None:
            return self._unavailable("Account creation time unavailable")
        now = datetime.now(timezone.utc)
        hours = (now - created).total_seconds() / 3600.0
        if hours < 1:
            return self._ok(True, 0.90, 0.99,
                            "Discord account created less than 1 hour ago")
        if hours < 6:
            return self._ok(True, 0.65, 0.95,
                            "Discord account created less than 6 hours ago")
        if hours < 24:
            return self._ok(True, 0.40, 0.90,
                            "Discord account created less than 24 hours ago")
        return self._ok(False, 0.0, 0.85, "Account older than 24 hours")


def _levenshtein(a: str, b: str, max_dist: int = 5) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_dist:
        return max_dist + 1
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        if i > max_dist:
            return max_dist + 1
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


class D43UsernamePatternCluster(Detector):
    """Detects genesis1 / genesis2 / g_enesis patterns against recent joins."""
    id = "USERNAME_PATTERN_CLUSTER"
    family = Family.BEHAVIOR
    evidence_type = "username_similarity"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        name = (ctx.member.name or "").lower().strip()
        if len(name) < 4:
            return self._ok(False, 0.0, 0.6, "Username too short for similarity analysis")

        recent = ctx.history.get("recent_usernames") or []
        if not recent:
            return self._unknown("No recent usernames to compare against")

        matches = 0
        for other_name, other_id in recent:
            if int(other_id) == ctx.member.id:
                continue
            other = str(other_name).lower().strip()
            if len(other) < 4:
                continue
            dist = _levenshtein(name, other, max_dist=2)
            if 1 <= dist <= 2:
                matches += 1

        if matches >= 3:
            return self._ok(True, 0.75, 0.80,
                            "Username similar to " + str(matches) + " recently-joined accounts")
        if matches >= 2:
            return self._ok(True, 0.50, 0.75,
                            "Username similar to " + str(matches) + " recently-joined accounts")
        if matches == 1:
            return self._ok(True, 0.20, 0.65,
                            "Username similar to 1 recently-joined account")
        return self._ok(False, 0.0, 0.70, "No username pattern matches")


class D44VerificationLatencyDelta(Detector):
    """Time between join and verify click. Bots click in seconds."""
    id = "VERIFICATION_LATENCY_DELTA"
    family = Family.BEHAVIOR
    evidence_type = "verification_timing"
    default_weight = 0.9

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.member.joined_at is None:
            return self._unavailable("Join time unavailable")
        now = datetime.now(timezone.utc)
        seconds_since_join = (now - ctx.member.joined_at).total_seconds()
        if seconds_since_join < 3:
            return self._ok(True, 0.70, 0.80,
                            "Clicked verify less than 3 seconds after joining")
        if seconds_since_join < 15:
            return self._ok(True, 0.40, 0.75,
                            "Clicked verify less than 15 seconds after joining")
        if seconds_since_join < 60:
            return self._ok(True, 0.15, 0.70,
                            "Clicked verify less than a minute after joining")
        return self._ok(False, 0.0, 0.75, "Organic verify timing")


class D45CrossAccountAgeDelta(Detector):
    """Discord + Roblox created within hours of each other."""
    id = "CROSS_ACCOUNT_AGE_DELTA"
    family = Family.CORRELATION
    evidence_type = "cross_age_delta"
    default_weight = 1.6

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.roblox is None or not ctx.roblox.available or not ctx.roblox.created_at:
            return self._unavailable("Roblox account not linked or creation date unknown")
        try:
            roblox_created = datetime.fromisoformat(str(ctx.roblox.created_at).replace("Z", "+00:00"))
            if roblox_created.tzinfo is None:
                roblox_created = roblox_created.replace(tzinfo=timezone.utc)
        except Exception:
            return self._unknown("Could not parse Roblox creation date")

        discord_created = ctx.member.created_at
        if discord_created is None:
            return self._unavailable("Discord creation date unavailable")

        delta_hours = abs((discord_created - roblox_created).total_seconds()) / 3600.0

        if delta_hours < 1:
            return self._ok(True, 0.90, 0.90,
                            "Discord and Roblox accounts created less than 1 hour apart")
        if delta_hours < 6:
            return self._ok(True, 0.70, 0.85,
                            "Discord and Roblox accounts created less than 6 hours apart")
        if delta_hours < 24:
            return self._ok(True, 0.45, 0.80,
                            "Discord and Roblox accounts created less than 24 hours apart")
        return self._ok(False, 0.0, 0.80, "Account creation dates are independent")


# ---------------------------------------------------------------------------
# PHASE-1 BEHAVIOURAL CORRELATION (46-50)
# Based on Discord-native signals: presence, voice, activity, session timing.
# No IPs. No content. No external APIs.
# ---------------------------------------------------------------------------
class D46PresenceTimelineCorrelation(Detector):
    id = "PRESENCE_TIMELINE_CORRELATION"
    family = Family.BEHAVIOR
    evidence_type = "presence_correlation"
    default_weight = 1.5

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        corr = ctx.history.get("presence_correlation")
        if corr is None:
            return self._unknown("No presence correlation data available yet")
        try:
            score = float(corr.get("score", 0.0))
        except Exception:
            return self._unknown("Malformed presence correlation data")
        if score >= 0.9:
            return self._ok(True, 0.85, 0.85,
                            "Presence timeline strongly correlates with another account")
        if score >= 0.75:
            return self._ok(True, 0.55, 0.75,
                            "Presence timeline matches another account")
        if score >= 0.6:
            return self._ok(True, 0.30, 0.65,
                            "Presence timeline partially matches another account")
        return self._ok(False, 0.0, 0.7, "No presence correlation")


class D47VoiceCoOccurrence(Detector):
    id = "VOICE_CO_OCCURRENCE"
    family = Family.BEHAVIOR
    evidence_type = "voice_correlation"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        corr = ctx.history.get("voice_correlation")
        if corr is None:
            return self._unknown("No voice correlation data available yet")
        try:
            score = float(corr.get("score", 0.0))
        except Exception:
            return self._unknown("Malformed voice correlation data")
        if score >= 0.9:
            return self._ok(True, 0.75, 0.80,
                            "Voice channel usage matches another account")
        if score >= 0.6:
            return self._ok(True, 0.45, 0.70,
                            "Voice channel usage partially matches another account")
        if score >= 0.5:
            return self._ok(True, 0.20, 0.60,
                            "Voice channel usage shares a channel with another account")
        return self._ok(False, 0.0, 0.65, "No voice correlation")


class D48SessionClustering(Detector):
    id = "SESSION_CLUSTERING"
    family = Family.BEHAVIOR
    evidence_type = "session_clustering"
    default_weight = 1.4

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        cluster = ctx.history.get("session_cluster")
        if cluster is None:
            return self._unknown("No session clustering data available yet")
        try:
            days = int(cluster.get("days", 0))
        except Exception:
            return self._unknown("Malformed session clustering data")
        if days >= 7:
            return self._ok(True, 0.80, 0.90,
                            "Login timing matches another account on " + str(days) + " separate days")
        if days >= 5:
            return self._ok(True, 0.55, 0.85,
                            "Login timing matches another account on " + str(days) + " separate days")
        if days >= 3:
            return self._ok(True, 0.30, 0.75,
                            "Login timing matches another account on " + str(days) + " separate days")
        return self._ok(False, 0.0, 0.7, "No login timing correlation")


class D49ActivityNameOverlap(Detector):
    id = "ACTIVITY_NAME_OVERLAP"
    family = Family.BEHAVIOR
    evidence_type = "activity_overlap"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        overlap = ctx.history.get("activity_overlap")
        if overlap is None:
            return self._unknown("No activity overlap data available yet")
        try:
            score = float(overlap.get("score", 0.0))
            shared = overlap.get("shared") or []
        except Exception:
            return self._unknown("Malformed activity overlap data")
        if score >= 0.9:
            return self._ok(True, 0.60, 0.70,
                            "Shares multiple niche activities with another account: " + ", ".join(shared[:3]))
        if score >= 0.5:
            return self._ok(True, 0.35, 0.60,
                            "Shares a niche activity with another account: " + ", ".join(shared[:3]))
        return self._ok(False, 0.0, 0.6, "No activity overlap")


class D50CrossAccountAgeWide(Detector):
    id = "CROSS_ACCOUNT_AGE_WIDE"
    family = Family.CORRELATION
    evidence_type = "cross_age_delta_wide"
    default_weight = 1.0

    async def evaluate(self, ctx: DetectorContext) -> DResult:
        if ctx.roblox is None or not ctx.roblox.available or not ctx.roblox.created_at:
            return self._unavailable("Roblox account not linked or creation date unknown")
        try:
            roblox_created = datetime.fromisoformat(str(ctx.roblox.created_at).replace("Z", "+00:00"))
            if roblox_created.tzinfo is None:
                roblox_created = roblox_created.replace(tzinfo=timezone.utc)
        except Exception:
            return self._unknown("Could not parse Roblox creation date")
        discord_created = ctx.member.created_at
        if discord_created is None:
            return self._unavailable("Discord creation date unavailable")
        delta_days = abs((discord_created - roblox_created).total_seconds()) / 86400.0
        if delta_days < 1:
            return self._ok(False, 0.0, 0.7, "Covered by narrower detector")
        if delta_days <= 7:
            return self._ok(True, 0.40, 0.75,
                            "Discord and Roblox accounts created within the same week")
        if delta_days <= 14:
            return self._ok(True, 0.20, 0.70,
                            "Discord and Roblox accounts created within the same fortnight")
        return self._ok(False, 0.0, 0.75, "Account creation dates are distant")


# ---------------------------------------------------------------------------
# Registry
#
# D14UnusualVerificationSpeed is NOT registered. See the class definition
# above for the reason. Total active detectors: 49.
# ---------------------------------------------------------------------------
ALL_DETECTORS: list[Detector] = [
    D01AccountAge(), D02UnusuallyNew(), D03ServerJoinAge(), D04RecentUsernameChange(),
    D05RecentDisplayNameChange(), D06AvatarReuse(), D07LowProfileActivity(), D08MutualServerPattern(),
    D09KnownBadAccountCorrelation(), D10AccountClusterPattern(),
    D11JoinBurst(), D12VerificationBurst(), D13RepeatedVerificationFailure(),
    D15UnusualVerificationDelay(), D16NewAccountJoinWave(), D17PostJoinBehavior(),
    D18RoleEscalationPattern(), D19RejoinPattern(), D20BanEvasionPattern(),
    D21RobloxAccountAge(), D22RobloxActivityLevel(), D23RobloxAccountReuse(),
    D24RobloxDiscordLinkHistory(), D25RobloxProfileAnomaly(), D26RobloxVerificationFailures(),
    D27RobloxLinkBurst(), D28RobloxClusterCorrelation(),
    D29Vpn(), D30Proxy(), D31Datacenter(), D32IpReputation(), D33Tor(),
    D34NetworkRiskScore(), D35IpVerificationVelocity(), D36InfrastructureCluster(),
    D37PreviousServerHistory(), D38PreviousVerificationHistory(), D39CrossSignalCorrelation(),
    D40KnownAbusePattern(),
    D41PublicFlags(), D42SnowflakePrecision(), D43UsernamePatternCluster(),
    D44VerificationLatencyDelta(), D45CrossAccountAgeDelta(),
    D46PresenceTimelineCorrelation(), D47VoiceCoOccurrence(), D48SessionClustering(),
    D49ActivityNameOverlap(), D50CrossAccountAgeWide(),
]


class DetectorRegistry:
    def __init__(self) -> None:
        self._detectors: dict[str, Detector] = {d.id: d for d in ALL_DETECTORS}

    def all(self) -> list[Detector]:
        return list(self._detectors.values())

    def get(self, detector_id: str) -> Optional[Detector]:
        return self._detectors.get(detector_id)

    def set_weight(self, detector_id: str, weight: float) -> bool:
        d = self._detectors.get(detector_id)
        if d is None:
            return False
        d.default_weight = max(0.0, float(weight))
        return True
