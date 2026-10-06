"""Confidence, correlation, historical, and clustering engines."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from bot.verification.detectors import DResult, DStatus, Family


class ConfidenceEngine:
    @staticmethod
    def effective(result: DResult) -> float:
        if result.status != DStatus.TRIGGERED or not result.triggered:
            return 0.0
        c = max(0.0, min(1.0, result.confidence))
        s = max(0.0, min(1.0, result.severity))
        # Handle negative severity (trust signals) separately
        if s < 0:
            return s * c
        if c < 0.3:
            c = c * 0.4
        elif c < 0.5:
            c = c * 0.75
        return s * c


class CorrelationEngine:
    INFRASTRUCTURE_FAMILIES = {Family.NETWORK}

    @staticmethod
    def family_caps() -> dict:
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
        by_key: dict = {}
        for r in results:
            if r.status != DStatus.TRIGGERED or not r.triggered:
                continue
            key = (r.signal_family, r.evidence_type)
            existing = by_key.get(key)
            eff = abs(ConfidenceEngine.effective(r))
            if existing is None or eff > abs(ConfidenceEngine.effective(existing)):
                by_key[key] = r

        grouped: dict = defaultdict(list)
        for r in by_key.values():
            grouped[r.signal_family].append(r)

        out: list[DResult] = []
        for fam, items in grouped.items():
            if fam in cls.INFRASTRUCTURE_FAMILIES and len(items) >= 2:
                for r in items:
                    out.append(DResult(
                        detector=r.detector, status=r.status, triggered=True,
                        severity=r.severity * 0.6, confidence=r.confidence,
                        score_contribution=r.score_contribution * 0.6,
                        evidence_type=r.evidence_type, signal_family=r.signal_family,
                        safe_reason=r.safe_reason, weight=r.weight,
                    ))
            else:
                out.extend(items)
        return out

    @classmethod
    def family_scores(cls, results: list[DResult]) -> dict:
        caps = cls.family_caps()
        collapsed = cls.collapse(results)
        scores: dict = defaultdict(float)
        for r in collapsed:
            weight = getattr(r, "weight", 1.0)
            scores[r.signal_family] += ConfidenceEngine.effective(r) * weight * 100.0
        for fam in list(scores.keys()):
            cap = caps.get(fam, 20.0)
            if scores[fam] > cap:
                scores[fam] = cap
            if scores[fam] < -cap:
                scores[fam] = -cap
        return scores

    @classmethod
    def correlation_bonus(cls, results: list[DResult]) -> float:
        fams = set()
        for r in results:
            if r.status == DStatus.TRIGGERED and r.triggered and r.severity > 0:
                fams.add(r.signal_family)
        n = len(fams)
        if n <= 1:
            return 0.0
        if n == 2:
            return 4.0
        if n == 3:
            return 10.0
        if n == 4:
            return 16.0
        return 22.0


@dataclass
class HistoricalRecord:
    category: str
    value: Any
    confidence: float = 0.8
    state: str = "SUSPICIOUS"
    age_days: int = 0


class HistoricalEngine:
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


@dataclass
class Cluster:
    cluster_id: str
    member_ids: set = field(default_factory=set)
    confidence: float = 0.0
    reasons: list = field(default_factory=list)


class ClusterEngine:
    @staticmethod
    def cluster_for(member_id: int, fingerprint_index: dict, fingerprint_rarity: dict) -> Cluster:
        member_fps = [fp for fp, ids in fingerprint_index.items() if member_id in ids]
        neighbors: dict = defaultdict(float)
        for fp in member_fps:
            rarity = fingerprint_rarity.get(fp, 0.5)
            for other in fingerprint_index.get(fp, set()):
                if other == member_id:
                    continue
                neighbors[other] += rarity

        cluster = Cluster(cluster_id="c_" + str(member_id), member_ids={member_id})
        if not neighbors:
            return cluster

        strong = {n: w for n, w in neighbors.items() if w >= 0.6}
        cluster.member_ids.update(strong.keys())
        if strong:
            confidence = min(sum(strong.values()) / (len(strong) + 1) / 2.0, 0.95)
            cluster.confidence = max(0.0, confidence)
            cluster.reasons.append(str(len(strong)) + " accounts share fingerprint(s)")
        return cluster
