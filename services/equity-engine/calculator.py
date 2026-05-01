"""Equity calculation logic."""

from typing import Dict, Any


class EquityCalculator:
    def calculate(self, appraisal_value: float, total_liens: float) -> Dict[str, Any]:
        """Compute equity amount and equity percentage."""
        # TODO: implement equity = appraisal_value - total_liens
        # TODO: account for senior vs junior lien priority
        raise NotImplementedError
