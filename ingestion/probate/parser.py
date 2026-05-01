"""Probate parser — transforms raw probate filings into structured records."""

from typing import List, Dict, Any


class ProbateParser:
    def parse(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse probate case records."""
        # TODO: extract estate address, case number, filing date, administrator contact
        raise NotImplementedError
