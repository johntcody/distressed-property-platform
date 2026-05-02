"""
Probate scraper configuration.

Strategy options:
  odyssey  — automated GET/POST against the Odyssey public portal
  manual   — county has no online access; operator must supply a CSV export

Decision gate from implementation-priority.md:
  "Odyssey access strategy (scrape vs. manual)" is resolved per county below.
  Burnet and Lee default to manual until online access is confirmed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProbateStrategy(str, Enum):
    odyssey = "odyssey"
    manual = "manual"


@dataclass
class ProbateCountyConfig:
    name: str
    strategy: ProbateStrategy
    odyssey_node_id: Optional[str] = None
    odyssey_url: Optional[str] = None
    notes: Optional[str] = None


PROBATE_COUNTY_CONFIGS = [
    ProbateCountyConfig(
        name="hays",
        strategy=ProbateStrategy.odyssey,
        odyssey_url="https://odyssey.co.hays.tx.us/PublicAccess/default.aspx",
        odyssey_node_id="1080",
        notes="Hays County Court at Law handles probate",
    ),
    ProbateCountyConfig(
        name="travis",
        strategy=ProbateStrategy.odyssey,
        odyssey_url="https://public.traviscountytx.gov/cgi-bin/coder.exe/coder",
        odyssey_node_id="1020",
        notes="Travis County Probate Court #1 and #2",
    ),
    ProbateCountyConfig(
        name="williamson",
        strategy=ProbateStrategy.odyssey,
        odyssey_url="https://judicialrecords.wilco.org/PublicAccess/default.aspx",
        odyssey_node_id="1180",
    ),
    ProbateCountyConfig(
        name="caldwell",
        strategy=ProbateStrategy.odyssey,
        odyssey_url="https://odyssey.caldwellcountytx.com/PublicAccess/default.aspx",
        odyssey_node_id="1040",
    ),
    ProbateCountyConfig(
        name="burnet",
        strategy=ProbateStrategy.manual,
        notes="Burnet County does not expose Odyssey publicly; manual CSV required",
    ),
    ProbateCountyConfig(
        name="bastrop",
        strategy=ProbateStrategy.odyssey,
        odyssey_url="https://odyssey.co.bastrop.tx.us/PublicAccess/default.aspx",
        odyssey_node_id="1030",
    ),
    ProbateCountyConfig(
        name="lee",
        strategy=ProbateStrategy.manual,
        notes="Lee County has no online probate search",
    ),
]

PROBATE_COUNTY_MAP = {c.name: c for c in PROBATE_COUNTY_CONFIGS}

ODYSSEY_PROBATE_TYPES = ["Probate", "Estate", "Guardianship", "Dependent Administration"]
