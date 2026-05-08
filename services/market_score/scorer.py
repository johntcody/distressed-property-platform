"""
Pure-Python market scoring logic — no framework dependency.

Market Score (0–100)
--------------------
Three equally-weighted sub-scores, each normalized to 0–100, then averaged:

  1. Appreciation score  — rewards high YoY price appreciation
  2. Liquidity score     — rewards low days-on-market (properties sell quickly)
  3. Yield score         — rewards high gross rent-to-price ratio

Thresholds are calibrated for the Central Texas market (Austin MSA).
Each sub-score is clamped to [0, 100] before averaging.

Sub-score formulas
------------------
appreciation_score = clamp((appreciation_rate / _APPRECIATION_MAX) * 100, 0, 100)
    _APPRECIATION_MAX = 0.15  (15% YoY → perfect score)

liquidity_score = clamp((1 - dom / _DOM_MAX) * 100, 0, 100)
    _DOM_MAX = 120  (≥120 days → score of 0; 0 days → 100)

yield_score = clamp((rent_to_price_ratio / _YIELD_MAX) * 100, 0, 100)
    _YIELD_MAX = 0.10  (10% gross yield → perfect score)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── calibration constants ─────────────────────────────────────────────────────

_APPRECIATION_MAX: float = 0.15   # 15% YoY → full appreciation sub-score
_DOM_MAX: float           = 120.0  # 120 days on market → zero liquidity sub-score
_YIELD_MAX: float         = 0.10   # 10% gross rent yield → full yield sub-score

_SCORE_VERSION = "1.0"


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class MarketInputs:
    """Inputs for a single market score calculation.

    All fields are optional — missing signals default to neutral (50-point)
    sub-scores so a partial data set still produces a usable result.
    """
    zip_code: str = ""

    # YoY appreciation as a decimal (e.g. 0.05 = 5%)
    appreciation_rate: Optional[float] = None

    # Average days on market for comparable properties in the area
    avg_days_on_market: Optional[float] = None

    # Gross rent-to-price ratio as a decimal (e.g. 0.07 = 7%)
    rent_to_price_ratio: Optional[float] = None


@dataclass
class MarketResult:
    zip_code: str
    market_score: float              # 0–100, rounded to 2 dp
    appreciation_score: float        # sub-score component
    liquidity_score: float           # sub-score component
    yield_score: float               # sub-score component
    inputs_used: dict                # echo of normalised inputs for raw_data storage
    score_version: str = _SCORE_VERSION


# ── scorer ────────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


class MarketScorer:

    def score(self, inputs: MarketInputs) -> MarketResult:
        """Compute a 0–100 market score from the supplied inputs."""

        # Sub-scores default to 50 (neutral) when the signal is absent
        if inputs.appreciation_rate is not None:
            appreciation_score = _clamp(inputs.appreciation_rate / _APPRECIATION_MAX * 100)
        else:
            appreciation_score = 50.0

        if inputs.avg_days_on_market is not None:
            liquidity_score = _clamp((1 - inputs.avg_days_on_market / _DOM_MAX) * 100)
        else:
            liquidity_score = 50.0

        if inputs.rent_to_price_ratio is not None:
            yield_score = _clamp(inputs.rent_to_price_ratio / _YIELD_MAX * 100)
        else:
            yield_score = 50.0

        market_score = round((appreciation_score + liquidity_score + yield_score) / 3, 2)

        return MarketResult(
            zip_code=inputs.zip_code,
            market_score=market_score,
            appreciation_score=round(appreciation_score, 2),
            liquidity_score=round(liquidity_score, 2),
            yield_score=round(yield_score, 2),
            inputs_used={
                "zip_code": inputs.zip_code,
                "appreciation_rate": inputs.appreciation_rate,
                "avg_days_on_market": inputs.avg_days_on_market,
                "rent_to_price_ratio": inputs.rent_to_price_ratio,
                "appreciation_score": round(appreciation_score, 2),
                "liquidity_score": round(liquidity_score, 2),
                "yield_score": round(yield_score, 2),
            },
        )
