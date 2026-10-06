"""Confidence, correlation, historical, and clustering engines."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from bot.verification.detectors import DResult, DStatus, Family


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------
class ConfidenceEngine:
    """Weights detector contributions by their confidence before scoring.

    - Detectors under 0.3 confidence get heavily damped.
    - Confidence multiplies but never exceeds 1.0.
    - UNAVAILABLE / UNKNOWN / ERROR contribute 0.
    """

    @staticmethod
    def effective(result: DResult) -> float:
        if result.status != DStatus.TRIGGERED or not result.triggered:
            return 0.0
        c = max(0.0, min(1.0, result.confidence))
        s = max(0.0, min(1.0, result.severity))
        # Damp low-confidence results aggressively
        if c < 0.3:
            c = c * 0.4
        elif c < 0.5:
            c = c * 0.75
        return s * c


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------
class CorrelationEngine:
    """Family grouping, duplicate suppression, and correlation bonus.

    Key rule: multiple observations of the same evidence_type within the same
    family are collapsed. Example: VPN + PROXY + DATACENTER all map to
    "network infrastructure" — they do not each add their full weight.
    """

    # Families where multiple detectors represent ONE underlying observation
    INFRASTRUCTURE_FAMILIES = {Family.NETWORK}

    @staticmethod
    def family_caps() -> dict[Family, float]:
        return {
            Family.DISCORD: 25.0,
            Family.BEHAVIOR: 30.0,
            Family.ROBLOX: 22.0,
            Family.NETWORK: 25.0,
            Family.DEVICE: 15.0,
            Family.BROWSER: 10.0,
            Family.HISTORICAL: 25.0,
            Family.CORRELATION: 18.0,
        }

    @classmethod
    def collapse(cls, results: list[DResult]) -> list[DResult]:
        """Collapse duplicate evidence_types within a family by keeping the max."""
        by_key: dict[tuple[Family, str], DResult] = {}
        for r in results:
            if r.status != DStatus.TRIGGERED or not r.triggered:
                continue
            key = (r.signal_family, r.evidence_type)
            existing = by_key.get(key)
            eff = ConfidenceEngine.effective(r)
            if existing is None or eff > ConfidenceEngine.effective(existing):
                by_key[key] = r

        # Additional damping for infrastructure families: if 2+ from same family,
        # apply 0.6 multiplier because they represent one underlying observation.
        grouped: dict[Family, list[DResult]] = defaultdict(list)
        for r in by_key.values():
            grouped[r.signal_family].append(r)

        out: list[DResult] = []
        for fam, items in grouped.items():
            if fam in cls.INFRASTRUCTURE_FAMILIES and len(items) >= 2:
                for r in items:
                    # clone with damped severity
                    out.append(DResult(
                        detector=r.detector, status=r.status, triggered=True,
                        severity=r.severity * 0.6, confidence=r.confidence,
                        score_contribution=r.score_contribution * 0.6,
                        evidence_type=r.evidence_type, signal_family=r.signal_family,
                        safe_reason=r.safe_reason,
                    ))
            else:
                out.extend(items)
        return out

    @classmethod
    def family_scores(cls, results: list[DResult]) -> dict[Family, float]:
        caps = cls.family_caps()
        collapsed = cls.collapse(results)
        scores: dict[Family, float] = defaultdict(float)
        for r in collapsed:
            scores[r.signal_family] += ConfidenceEngine.effective(r) * r.detector_weight_if_any() * 100.0
        for fam in list(scores.keys()):
            cap = caps.get(fam, 20.0)
            if scores[fam] > cap:
                scores[fam] = cap
        return scores

    @classmethod
    def correlation_bonus(cls, results: list[DResult]) -> float:
        fams = set()
        for r in results:
            if r.status == DStatus.TRIGGERED and r.triggered:
                fams.add(r.signal_family)
        n = len(fams)
        if n <= 1: return 0.0
        if n == 2: return 4.0
        if n == 3: return 10.0
        if n == 4: return 16.0
        return 22.0


# ---------------------------------------------------------------------------
# Historical
# ---------------------------------------------------------------------------
@dataclass
class HistoricalRecord:
    category: str        # e.g. "user_prior_quarantines"
    value: Any
    confidence: float = 0.8
    state: str = "SUSPICIOUS"    # CONFIRMED | LIKELY | SUSPICIOUS | UNKNOWN | FALSE_POSITIVE | EXPIRED
    age_days: int = 0


class HistoricalEngine:
    """Decays historical evidence and drops FALSE_POSITIVE / EXPIRED records."""

    HALF_LIFE_DAYS = 30.0

    @classmethod
    def decay(cls, record: HistoricalRecord) -> float:
        if record.state in ("FALSE_POSITIVE", "EXPIRED"):
            return 0.0
        if record.state == "CONFIRMED":
            base = 1.0
        elif record.state == "LIKELY":
            base = 0.7
        elif record.state == "SUSPICIOUS":
            base = 0.4
        else:
            base = 0.2
        decayed = base * math.pow(0.5, record.age_days / cls.HALF_LIFE_DAYS)
        return max(0.0, min(1.0, decayed * record.confidence))


# ---------------------------------------------------------------------------
# Cluster engine
# ---------------------------------------------------------------------------
@dataclass
class Cluster:
    cluster_id: str
    member_ids: set[int] = field(default_factory=set)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)


class ClusterEngine:
    """Builds account clusters based on shared fingerprints.

    Cluster confidence is derived from how many fingerprints two accounts share
    and how rare those fingerprints are. The engine NEVER claims accounts belong
    to the same person — only that they exhibit correlated security characteristics.
    """

    @staticmethod
    def cluster_for(member_id: int, fingerprint_index: dict[str, set[int]],
                    fingerprint_rarity: dict[str, float]) -> Cluster:
        member_fps = [fp for fp, ids in fingerprint_index.items() if member_id in ids]
        neighbors: dict[int, float] = defaultdict(float)
        for fp in member_fps:
            rarity = fingerprint_rarity.get(fp, 0.5)
            for other in fingerprint_index.get(fp, set()):
                if other == member_id:
                    continue
                neighbors[other] += rarity

        cluster = Cluster(cluster_id=f"c_{member_id}", member_ids={member_id})
        if not neighbors:
            return cluster

        # Keep neighbors with meaningful shared weight
        strong = {n: w for n, w in neighbors.items() if w >= 0.6}
        cluster.member_ids.update(strong.keys())
        if strong:
            confidence = min(sum(strong.values()) / (len(strong) + 1) / 2.0, 0.95)
            cluster.confidence = max(0.0, confidence)
            cluster.reasons.append(f"{len(strong)} accounts share fingerprint(s)")
        return cluster
