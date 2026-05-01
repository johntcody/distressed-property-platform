"""Rehab cost estimation logic."""

from typing import Dict, Any


COST_PER_SQFT = {
    "light": 15,
    "moderate": 35,
    "heavy": 65,
    "full_gut": 100,
}


class RehabEstimator:
    def estimate(self, sqft: int, condition: str, extras: Dict[str, Any] = None) -> float:
        """Estimate rehab cost based on square footage and condition level."""
        # TODO: implement line-item breakdown (roof, HVAC, plumbing, kitchen, baths)
        raise NotImplementedError
