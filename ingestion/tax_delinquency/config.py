"""Per-county configuration for tax delinquency sources."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SourceFormat(str, Enum):
    csv = "csv"
    pdf = "pdf"
    html = "html"


@dataclass
class TaxCountyConfig:
    name: str
    listing_url: str
    source_format: SourceFormat
    appraisal_district: str
    notes: Optional[str] = None


TAX_COUNTY_CONFIGS = [
    TaxCountyConfig(
        name="hays",
        listing_url="https://www.hayscad.com/delinquent-tax-rolls",
        source_format=SourceFormat.csv,
        appraisal_district="Hays CAD",
    ),
    TaxCountyConfig(
        name="travis",
        listing_url="https://tax.traviscountytx.gov/delinquent",
        source_format=SourceFormat.html,
        appraisal_district="Travis CAD",
        notes="HTML table; search by owner name or address",
    ),
    TaxCountyConfig(
        name="williamson",
        listing_url="https://www.wcad.org/delinquent-tax-list",
        source_format=SourceFormat.csv,
        appraisal_district="Williamson CAD",
    ),
    TaxCountyConfig(
        name="caldwell",
        listing_url="https://www.caldwellcad.org/delinquent",
        source_format=SourceFormat.pdf,
        appraisal_district="Caldwell CAD",
    ),
    TaxCountyConfig(
        name="burnet",
        listing_url="https://www.burnetcad.org/delinquent-tax",
        source_format=SourceFormat.csv,
        appraisal_district="Burnet CAD",
    ),
    TaxCountyConfig(
        name="bastrop",
        listing_url="https://www.bastropcad.org/delinquent-rolls",
        source_format=SourceFormat.csv,
        appraisal_district="Bastrop CAD",
    ),
    TaxCountyConfig(
        name="lee",
        listing_url="https://www.leecad.org/delinquent",
        source_format=SourceFormat.pdf,
        appraisal_district="Lee CAD",
        notes="Small county; may require manual PDF download",
    ),
]

TAX_COUNTY_MAP = {c.name: c for c in TAX_COUNTY_CONFIGS}
