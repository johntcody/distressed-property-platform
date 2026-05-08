"""
Pure-Python MAO (Maximum Allowable Offer) calculation logic.

Formula
-------
  MAO = (ARV × discount_pct / 100) − rehab_cost − holding_costs − closing_costs

All monetary inputs are USD. discount_pct is a percentage (e.g. 70.0 = 70%).
"""

from __future__ import annotations

from dataclasses import dataclass, field


_MAO_VERSION = "1.0"


@dataclass
class MAOInputs:
    arv:           float                   # USD — after-repair value
    rehab_cost:    float                   # USD — total rehab estimate
    discount_pct:  float = 70.0            # % of ARV to target (0–100)
    holding_costs: float = 0.0            # USD — taxes, insurance, financing
    closing_costs: float = 0.0            # USD — title, agent, transfer fees


@dataclass
class MAOResult:
    arv:           float
    discount_pct:  float
    rehab_cost:    float
    holding_costs: float
    closing_costs: float
    mao:           float                   # USD — maximum allowable offer
    mao_version:   str = field(default=_MAO_VERSION)


class MAOCalculator:

    def calculate(self, inputs: MAOInputs) -> MAOResult:
        if inputs.arv <= 0:
            raise ValueError(f"arv must be positive, got {inputs.arv}")
        if not (0 < inputs.discount_pct <= 100):
            raise ValueError(
                f"discount_pct must be between 0 and 100 (exclusive/inclusive), "
                f"got {inputs.discount_pct}"
            )
        if inputs.rehab_cost < 0:
            raise ValueError(f"rehab_cost must be non-negative, got {inputs.rehab_cost}")
        if inputs.holding_costs < 0:
            raise ValueError(f"holding_costs must be non-negative, got {inputs.holding_costs}")
        if inputs.closing_costs < 0:
            raise ValueError(f"closing_costs must be non-negative, got {inputs.closing_costs}")

        mao = round(
            (inputs.arv * inputs.discount_pct / 100)
            - inputs.rehab_cost
            - inputs.holding_costs
            - inputs.closing_costs,
            2,
        )

        return MAOResult(
            arv=inputs.arv,
            discount_pct=inputs.discount_pct,
            rehab_cost=inputs.rehab_cost,
            holding_costs=inputs.holding_costs,
            closing_costs=inputs.closing_costs,
            mao=mao,
        )
