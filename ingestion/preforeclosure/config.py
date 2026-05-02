"""Per-county configuration for pre-foreclosure / Lis Pendens sources (district clerk portals)."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PreforeclosureCountyConfig:
    name: str
    search_url: str
    court_type: str
    search_keywords: List[str] = field(default_factory=lambda: [
        "Lis Pendens", "Foreclosure", "Default Judgment", "Deed of Trust"
    ])
    notes: Optional[str] = None


PREFORECLOSURE_COUNTY_CONFIGS = [
    PreforeclosureCountyConfig(
        name="hays",
        search_url="https://public.co.hays.tx.us/search.aspx",
        court_type="district",
    ),
    PreforeclosureCountyConfig(
        name="travis",
        search_url="https://public.traviscountytx.gov/cgi-bin/coder.exe/coder",
        court_type="district",
        notes="Legacy CGI search; keyword param is 'CaseStyle'",
    ),
    PreforeclosureCountyConfig(
        name="williamson",
        search_url="https://judicialrecords.wilco.org/PublicAccess/default.aspx",
        court_type="district",
    ),
    PreforeclosureCountyConfig(
        name="caldwell",
        search_url="https://www.caldwellcountytx.com/district-clerk/case-search",
        court_type="district",
    ),
    PreforeclosureCountyConfig(
        name="burnet",
        search_url="https://www.burnetcountytexas.org/district-clerk/public-search",
        court_type="district",
    ),
    PreforeclosureCountyConfig(
        name="bastrop",
        search_url="https://www.co.bastrop.tx.us/page/dc.case_search",
        court_type="district",
    ),
    PreforeclosureCountyConfig(
        name="lee",
        search_url="https://www.co.lee.tx.us/district-clerk/search",
        court_type="district",
        notes="Lee county may not have online search; manual review may be required",
    ),
]

PREFORECLOSURE_COUNTY_MAP = {c.name: c for c in PREFORECLOSURE_COUNTY_CONFIGS}

LP_KEYWORDS = ["lis pendens", "foreclosure", "default", "deed of trust", "lien"]
