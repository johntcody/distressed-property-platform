"""Distress scoring logic."""

from typing import Dict, Any


class DistressScorer:
    """Computes a 0-100 distress score based on property event signals."""

    WEIGHTS = {
        "foreclosure": 0.4,
        "tax_delinquency": 0.3,
        "preforeclosure": 0.2,
        "probate": 0.1,
    }

    def score(self, property_data: Dict[str, Any]) -> float:
        """Return a distress score for the given property."""
        # TODO: implement weighted scoring across distress signals
        raise NotImplementedError

    def _normalize(self, raw_score: float) -> float:
        """Clamp score to [0, 100]."""
        return max(0.0, min(100.0, raw_score))
