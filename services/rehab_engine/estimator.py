"""
Pure-Python rehab cost estimation logic — no framework dependency.

Rehab Cost Model
----------------
Three templates calibrated for Central Texas single-family residential:

  light  — cosmetic only (paint, flooring, fixtures, landscaping)
  medium — systems work (HVAC, plumbing, electrical) plus cosmetics
  heavy  — structural / full systems renovation

Each template is composed of configurable line items. The caller may supply
per-line-item overrides to replace the template defaults.

Output
------
RehabResult contains:
  total_cost   — sum of all line items after overrides
  cost_per_sqft — total_cost / sqft
  line_items   — dict of {name: cost} for transparency
  rehab_level  — the template used
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── default cost-per-sqft templates ──────────────────────────────────────────
# Values represent cost in USD per square foot for each line item.
# Overrides passed by the caller replace individual entries.

_TEMPLATES: dict[str, dict[str, float]] = {
    "light": {
        "paint":        4.00,
        "flooring":     6.00,
        "fixtures":     2.00,
        "landscaping":  1.50,
        "cleaning":     0.50,
    },
    "medium": {
        "paint":        4.00,
        "flooring":     8.00,
        "fixtures":     3.00,
        "landscaping":  1.50,
        "cleaning":     0.50,
        "hvac":         5.00,
        "plumbing":     4.00,
        "electrical":   3.00,
        "kitchen":      6.00,
        "bathrooms":    5.00,
    },
    "heavy": {
        "paint":        4.00,
        "flooring":    10.00,
        "fixtures":     4.00,
        "landscaping":  2.00,
        "cleaning":     0.50,
        "hvac":         8.00,
        "plumbing":     7.00,
        "electrical":   6.00,
        "kitchen":     12.00,
        "bathrooms":    9.00,
        "roof":        10.00,
        "foundation":   8.00,
        "windows":      4.00,
        "doors":        2.00,
    },
}

_REHAB_VERSION = "1.0"

VALID_LEVELS = frozenset(_TEMPLATES)


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class RehabInputs:
    """Inputs for a single rehab cost estimate."""
    sqft: float
    rehab_level: str = "medium"           # "light" | "medium" | "heavy"
    overrides: dict[str, float] = field(default_factory=dict)
    # per-sqft overrides: {"hvac": 6.50} replaces template value for that item


@dataclass
class RehabResult:
    rehab_level: str
    sqft: float
    total_cost: float                     # USD
    cost_per_sqft: float                  # USD / sqft
    line_items: dict[str, float]          # {item_name: total_cost_for_item}
    rehab_version: str = _REHAB_VERSION


# ── estimator ─────────────────────────────────────────────────────────────────

class RehabEstimator:

    def estimate(self, inputs: RehabInputs) -> RehabResult:
        """Compute a rehab cost estimate from the template plus caller overrides."""
        if inputs.rehab_level not in VALID_LEVELS:
            raise ValueError(
                f"rehab_level must be one of {sorted(VALID_LEVELS)!r}, "
                f"got {inputs.rehab_level!r}"
            )
        if inputs.sqft <= 0:
            raise ValueError(f"sqft must be positive, got {inputs.sqft}")
        negative = [k for k, v in inputs.overrides.items() if v < 0]
        if negative:
            raise ValueError(f"override rates must be non-negative; got negative values for {negative!r}")

        template = dict(_TEMPLATES[inputs.rehab_level])
        template.update(inputs.overrides)   # caller overrides replace defaults

        line_items = {
            name: round(rate * inputs.sqft, 2)
            for name, rate in template.items()
        }
        total_cost   = round(sum(line_items.values()), 2)
        cost_per_sqft = round(total_cost / inputs.sqft, 2)

        return RehabResult(
            rehab_level=inputs.rehab_level,
            sqft=inputs.sqft,
            total_cost=total_cost,
            cost_per_sqft=cost_per_sqft,
            line_items=line_items,
        )
