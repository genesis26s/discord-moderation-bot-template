"""Risk engine + 5-layer policy."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from bot.verification.detectors import DResult, DStatus, Family
from bot.verification.engines import ConfidenceEngine, CorrelationEngine


class RiskLevel(str, Enum):
    LOW = "LOW"
    GUARDED = "GUARDED"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RequiredLayer(int, Enum):
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4
    L5 = 5


@dataclass
class Thresholds:
    guarded: float = 20.0
    elevated: float = 40.0
    high: float = 60.0
    critical: float = 80.0


@dataclass
class RiskVerdict:
    risk_score: int
    risk_level: RiskLevel
    confidence: float
    detections: list[DResult]
    safe_reasons: list[str]
    required_layer: RequiredLayer
    recommendation: str
    assessment_id: Optional[int] = None
    triggered_families: set[Family] = field(default_factory=set)


class RiskEngine:
    def __init__(self, thresholds: Optional[Thresholds] = None) -> None:
        self.thresholds = thresholds or Thresholds()

    def level_for(self, score: float) -> RiskLevel:
        t = self.thresholds
        if score >= t.critical: return RiskLevel.CRITICAL
        if score >= t.high:     return RiskLevel.HIGH
        if score >= t.elevated: return RiskLevel.ELEVATED
        if score >= t.guarded:  return RiskLevel.GUARDED
        return RiskLevel.LOW

    def layer_for(self, level: RiskLevel) -> RequiredLayer:
        return {
            RiskLevel.LOW:      RequiredLayer.L1,
            RiskLevel.GUARDED:  RequiredLayer.L2,
            RiskLevel.ELEVATED: RequiredLayer.L3,
            RiskLevel.HIGH:     RequiredLayer.L4,
            RiskLevel.CRITICAL: RequiredLayer.L5,
        }[level]

    def recommendation_for(self, level: RiskLevel) -> str:
        return {
            RiskLevel.LOW:      "Standard verification",
            RiskLevel.GUARDED:  "Enhanced verification",
            RiskLevel.ELEVATED: "Correlation review",
            RiskLevel.HIGH:     "Restricted verification with moderator review eligibility",
            RiskLevel.CRITICAL: "Quarantine and manual review",
        }[level]

    def evaluate(self, results: list[DResult]) -> RiskVerdict:
        triggered = [r for r in results if r.status == DStatus.TRIGGERED and r.triggered]

        # Per-family scoring (deduplicated + capped)
        fam_scores = CorrelationEngine.family_scores(results)
        raw = sum(fam_scores.values())

        # Correlation bonus (independent families firing together)
        bonus = CorrelationEngine.correlation_bonus(triggered)

        # Confidence aggregation: high-severity items carry more weight
        if triggered:
            confidence = min(
                0.99,
                sum(ConfidenceEngine.effective(r) for r in triggered) /
                max(len(triggered), 1) * 1.6,
            )
        else:
            confidence = 0.5

        # Never let a single family alone reach the top of the scale.
        max_contribution = sum(CorrelationEngine.family_caps().values())
        total = min(raw + bonus, 100.0)

        score = int(round(total))
        level = self.level_for(score)
        layer = self.layer_for(level)

        safe_reasons = [r.safe_reason for r in triggered]
        fams = {r.signal_family for r in triggered}

        return RiskVerdict(
            risk_score=score,
            risk_level=level,
            confidence=round(confidence, 3),
            detections=results,
            safe_reasons=safe_reasons,
            required_layer=layer,
            recommendation=self.recommendation_for(level),
            triggered_families=fams,
        )
