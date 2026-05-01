"""Foreclosure parser — transforms raw HTML/JSON into structured records."""

from typing import List, Dict, Any


class ForeclosureParser:
    def parse(self, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse raw records into normalized property events."""
        # TODO: implement field extraction (address, case number, auction date, etc.)
        raise NotImplementedError

    def normalize_address(self, raw_address: str) -> str:
        """Standardize address format."""
        # TODO: integrate with address normalization library
        return raw_address.strip()
