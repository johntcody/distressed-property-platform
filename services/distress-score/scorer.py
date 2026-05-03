"""Distress scoring logic — weighted model across four distress signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ingestion.shared.models import ForeclosureStage

# ── Per-signal maximums (all normalised to 0–100 before weighting) ─────────────

_STAGE_SCORES: dict[str | None, float] = {
    ForeclosureStage.NOD.value:     40.0,
    ForeclosureStage.NTS.value:     75.0,
    ForeclosureStage.auction.value: 100.0,
    ForeclosureStage.REO.value:     60.0,
    None:                            0.0,
}

# Tax delinquency: 15 pts per year, capped at 100
_TAX_PTS_PER_YEAR = 15.0
_TAX_CAP          = 100.0

# Pre-foreclosure recency: 100 pts day-of-filing, decaying to 0 at 300 days
_LP_DECAY_DAYS = 300.0

# Weights must sum to 1.0
_WEIGHTS = {
    "foreclosure":    0.40,
    "tax_delinquency": 0.30,
    "preforeclosure": 0.20,
    "probate":        0.10,
}


@dataclass
class DistressSignals:
    """All inputs the scorer needs — caller populates from DB query results."""

    # Foreclosure
    foreclosure_stage: Optional[str] = None        # ForeclosureStage value or None

    # Tax delinquency
    years_delinquent: Optional[int] = None         # most-recent tax delinquency years

    # Probate
    has_active_probate: bool = False

    # Pre-foreclosure
    lp_filing_date: Optional[date] = None          # date of most-recent Lis Pendens

    # Reference date for recency calculations (defaults to today)
    as_of: Optional[date] = None


@dataclass
class DistressScoreResult:
    score: float                    # 0–100, two-decimal precision
    foreclosure_component: float
    tax_component: float
    preforeclosure_component: float
    probate_component: float
    score_version: str = "1.0"


class DistressScorer:
    """Computes a 0–100 distress score from four weighted signals."""

    def score(self, signals: DistressSignals) -> DistressScoreResult:
        fc  = self._foreclosure_component(signals.foreclosure_stage)
        tax = self._tax_component(signals.years_delinquent)
        lp  = self._preforeclosure_component(signals.lp_filing_date, signals.as_of)
        pb  = self._probate_component(signals.has_active_probate)

        composite = (
            fc  * _WEIGHTS["foreclosure"]
            + tax * _WEIGHTS["tax_delinquency"]
            + lp  * _WEIGHTS["preforeclosure"]
            + pb  * _WEIGHTS["probate"]
        )

        return DistressScoreResult(
            score=round(self._clamp(composite), 2),
            foreclosure_component=round(fc, 2),
            tax_component=round(tax, 2),
            preforeclosure_component=round(lp, 2),
            probate_component=round(pb, 2),
        )

    # ── private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _foreclosure_component(stage: Optional[str]) -> float:
        return _STAGE_SCORES.get(stage, 0.0)

    @staticmethod
    def _tax_component(years: Optional[int]) -> float:
        if not years or years <= 0:
            return 0.0
        return min(years * _TAX_PTS_PER_YEAR, _TAX_CAP)

    @staticmethod
    def _preforeclosure_component(filing_date: Optional[date], as_of: Optional[date]) -> float:
        if not filing_date:
            return 0.0
        ref = as_of or date.today()
        days_elapsed = max(0, (ref - filing_date).days)
        return max(0.0, 100.0 * (1.0 - days_elapsed / _LP_DECAY_DAYS))

    @staticmethod
    def _probate_component(active: bool) -> float:
        return 100.0 if active else 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(100.0, value))
