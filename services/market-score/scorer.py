"""Market scoring logic."""

from typing import Dict, Any


class MarketScorer:
    def score(self, market_data: Dict[str, Any]) -> float:
        """Return a 0-100 market strength score."""
        # TODO: incorporate median price trend, DOM, absorption rate, list-to-sale ratio
        raise NotImplementedError
