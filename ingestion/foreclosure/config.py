"""Per-county configuration for foreclosure posting sources."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CountyConfig:
    name: str
    listing_url: str                  # page that lists available posting PDFs
    pdf_base_url: str                 # prefix for relative PDF hrefs
    link_pattern: str                 # regex to match PDF hrefs on the listing page
    auction_day: str                  # e.g. "first tuesday"
    notes: Optional[str] = None


COUNTY_CONFIGS: List[CountyConfig] = [
    CountyConfig(
        name="hays",
        listing_url="https://www.co.hays.tx.us/foreclosure-notices.aspx",
        pdf_base_url="https://www.co.hays.tx.us",
        link_pattern=r"(?i)foreclosure.*\.pdf",
        auction_day="first tuesday",
        notes="Lists monthly notice PDFs; new postings appear ~5th of prior month",
    ),
    CountyConfig(
        name="travis",
        listing_url="https://www.traviscountytx.gov/courts/county-clerk/foreclosure-notices",
        pdf_base_url="https://www.traviscountytx.gov",
        link_pattern=r"(?i)(foreclosure|notice).*\.pdf",
        auction_day="first tuesday",
    ),
    CountyConfig(
        name="williamson",
        listing_url="https://www.wilco.org/Departments/County-Clerk/Foreclosure-Notices",
        pdf_base_url="https://www.wilco.org",
        link_pattern=r"(?i)foreclosure.*\.pdf",
        auction_day="first tuesday",
    ),
    CountyConfig(
        name="caldwell",
        listing_url="https://www.caldwellcountytx.com/county-clerk/foreclosure-notices",
        pdf_base_url="https://www.caldwellcountytx.com",
        link_pattern=r"(?i)(foreclosure|notice).*\.pdf",
        auction_day="first tuesday",
    ),
    CountyConfig(
        name="burnet",
        listing_url="https://www.burnetcountytexas.org/county-clerk/foreclosure",
        pdf_base_url="https://www.burnetcountytexas.org",
        link_pattern=r"(?i)foreclosure.*\.pdf",
        auction_day="first tuesday",
    ),
    CountyConfig(
        name="bastrop",
        listing_url="https://www.co.bastrop.tx.us/page/co.clerk_foreclosure",
        pdf_base_url="https://www.co.bastrop.tx.us",
        link_pattern=r"(?i)(foreclosure|notice).*\.pdf",
        auction_day="first tuesday",
    ),
    CountyConfig(
        name="lee",
        listing_url="https://www.co.lee.tx.us/county-clerk/foreclosure-notices",
        pdf_base_url="https://www.co.lee.tx.us",
        link_pattern=r"(?i)foreclosure.*\.pdf",
        auction_day="first tuesday",
        notes="Small county; postings may be combined with general clerk notices",
    ),
]

COUNTY_MAP = {c.name: c for c in COUNTY_CONFIGS}
