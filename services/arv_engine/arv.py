"""
Pure-Python ARV calculation logic — no framework dependency.

ARV (After-Repair Value)
------------------------
Computed from comparable sales using inverse-distance-weighted price-per-sqft:

  1. Fetch comps from provider (stub until COMP_PROVIDER is wired)
  2. Filter:
       - beds and baths must match subject exactly
       - sqft within ±20% of subject
       - sold within the last 12 months
  3. Weight each comp by 1 / (distance_miles + 0.1)  (avoid divide-by-zero)
  4. ARV = weighted_avg_price_per_sqft × subject_sqft

Confidence tiers (based on filtered comp count)
------------------------------------------------
  ≥5 comps  → 90
  3–4 comps → 70
  1–2 comps → 50
  0 comps   → 0  (no estimate possible)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


# ── calibration ───────────────────────────────────────────────────────────────

_SQFT_TOLERANCE   = 0.20   # ±20%
_LOOKBACK_DAYS    = 365    # 12-month comp window
_DISTANCE_OFFSET  = 0.1    # miles added to distance to avoid ÷0

_ARV_VERSION = "1.0"


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class SubjectProperty:
    property_id: str
    sqft: float
    beds: int
    baths: float
    zip_code: str = ""


@dataclass
class Comp:
    """A single comparable sale."""
    sale_price: float
    sqft: float
    beds: int
    baths: float
    sale_date: date
    distance_miles: float


@dataclass
class ARVResult:
    property_id: str
    arv: Optional[float]        # None when comp_count == 0
    arv_confidence: float       # 0–100
    comp_count: int
    method: str
    arv_version: str = _ARV_VERSION


# ── comp provider stub ────────────────────────────────────────────────────────

def _get_comps(subject: SubjectProperty) -> list[Comp]:
    """Return comparable sales for subject.

    Set COMP_PROVIDER=attom (or similar) and implement the real call here.
    Until then, returns an empty list so the service starts cleanly and
    callers receive confidence=0 / arv=None.
    """
    provider = os.environ.get("COMP_PROVIDER", "stub")
    if provider == "stub":
        return []
    raise NotImplementedError(f"COMP_PROVIDER={provider!r} not implemented")


# ── filtering ─────────────────────────────────────────────────────────────────

def _filter_comps(subject: SubjectProperty, comps: list[Comp]) -> list[Comp]:
    cutoff = date.today() - timedelta(days=_LOOKBACK_DAYS)
    sqft_lo = subject.sqft * (1 - _SQFT_TOLERANCE)
    sqft_hi = subject.sqft * (1 + _SQFT_TOLERANCE)

    return [
        c for c in comps
        if c.sqft > 0                      # guard against provider data quality issues
        and c.distance_miles >= 0
        and c.beds == subject.beds
        and c.baths == subject.baths
        and sqft_lo <= c.sqft <= sqft_hi
        and c.sale_date >= cutoff
    ]


# ── weighting ─────────────────────────────────────────────────────────────────

def _weighted_price_per_sqft(comps: list[Comp]) -> float:
    """Inverse-distance-weighted average price-per-sqft."""
    weights = [1.0 / (c.distance_miles + _DISTANCE_OFFSET) for c in comps]
    total_w = sum(weights)
    ppsf_values = [c.sale_price / c.sqft for c in comps]
    return sum(w * ppsf for w, ppsf in zip(weights, ppsf_values)) / total_w


# ── confidence ────────────────────────────────────────────────────────────────

def _confidence(comp_count: int) -> float:
    if comp_count >= 5:
        return 90.0
    if comp_count >= 3:
        return 70.0
    if comp_count >= 1:
        return 50.0
    return 0.0


# ── calculator ────────────────────────────────────────────────────────────────

class ARVCalculator:

    def estimate(self, subject: SubjectProperty) -> ARVResult:
        """Compute ARV for subject using filtered, weighted comps."""
        raw_comps = _get_comps(subject)
        filtered  = _filter_comps(subject, raw_comps)
        count     = len(filtered)

        if count == 0:
            return ARVResult(
                property_id=subject.property_id,
                arv=None,
                arv_confidence=0.0,
                comp_count=0,
                method="price_per_sqft",
            )

        ppsf = _weighted_price_per_sqft(filtered)
        arv  = round(ppsf * subject.sqft, 2)

        return ARVResult(
            property_id=subject.property_id,
            arv=arv,
            arv_confidence=_confidence(count),
            comp_count=count,
            method="price_per_sqft",
        )
