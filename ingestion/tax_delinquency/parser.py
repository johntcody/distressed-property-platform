"""Tax delinquency parser — transforms raw records into structured events."""

from typing import List, Dict, Any


class TaxDelinquencyParser:
    def parse(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse raw tax delinquency records."""
        # TODO: extract CAD account number, owner, amount owed, years delinquent
        raise NotImplementedError
