"""ARV calculation logic."""

from typing import List, Dict, Any


class ARVCalculator:
    def estimate(self, subject: Dict[str, Any], comps: List[Dict[str, Any]]) -> float:
        """Estimate ARV using adjusted comparable sales (price per sqft method)."""
        # TODO: filter comps by proximity, age, sqft range
        # TODO: apply condition adjustments
        # TODO: return weighted average of adjusted comp values
        raise NotImplementedError
