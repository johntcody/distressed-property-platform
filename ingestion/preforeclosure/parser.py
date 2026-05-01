"""Pre-foreclosure parser — transforms NOD/lis pendens records into structured events."""

from typing import List, Dict, Any


class PreforeclosureParser:
    def parse(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse pre-foreclosure records."""
        # TODO: extract property address, lender, filing date, loan amount
        raise NotImplementedError
