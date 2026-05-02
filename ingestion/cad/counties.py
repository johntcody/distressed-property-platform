"""
County CAD (Central Appraisal District) data source configurations.

Texas CAD data is public record. Each county publishes annual bulk exports
in CSV or DBF format. These URLs and field mappings are county-specific.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CadCountyConfig:
    name: str
    fips: str                        # 5-digit FIPS code
    cad_name: str                    # Official CAD entity name
    portal_url: str                  # Human-readable portal (for reference)
    bulk_export_url: Optional[str]   # Direct CSV/ZIP download, if available
    export_format: str               # "csv" | "dbf" | "xlsx" | "manual"
    # Column mapping: standard name -> county-specific column header
    column_map: dict = field(default_factory=dict)
    notes: str = ""


COUNTY_CONFIGS: dict[str, CadCountyConfig] = {
    "hays": CadCountyConfig(
        name="Hays",
        fips="48209",
        cad_name="Hays Central Appraisal District",
        portal_url="https://hayscad.com",
        bulk_export_url=None,  # Must request via open-records or use PTAD
        export_format="manual",
        column_map={
            "apn": "AccountNumber",
            "owner_name": "OwnerName",
            "address_raw": "SitusAddress",
            "city": "SitusCity",
            "zip_code": "SitusZip",
            "land_value": "LandValue",
            "improvement_value": "ImprovementValue",
            "total_value": "TotalAppraisedValue",
            "sqft": "ImprovSqFt",
            "year_built": "YearBuilt",
            "bedrooms": "Bedrooms",
            "bathrooms": "Bathrooms",
        },
        notes="Request bulk export via open-records; PTAD also publishes annual file",
    ),
    "travis": CadCountyConfig(
        name="Travis",
        fips="48453",
        cad_name="Travis Central Appraisal District",
        portal_url="https://www.traviscad.org",
        bulk_export_url="https://www.traviscad.org/wp-content/uploads/",  # Approximate; check portal for current year
        export_format="csv",
        column_map={
            "apn": "Prop_ID",
            "owner_name": "Owner_Name",
            "address_raw": "Situs_Addr",
            "city": "Situs_City",
            "zip_code": "Situs_Zip",
            "land_value": "Land_Val",
            "improvement_value": "Impr_Val",
            "total_value": "Appr_Val",
            "sqft": "Living_Area",
            "year_built": "Yr_Built",
            "bedrooms": "Bedrooms",
            "bathrooms": "Bathrooms",
        },
        notes="Travis CAD publishes annual export; also available via PTAD bulk file",
    ),
    "williamson": CadCountyConfig(
        name="Williamson",
        fips="48491",
        cad_name="Williamson Central Appraisal District",
        portal_url="https://www.wcad.org",
        bulk_export_url=None,
        export_format="manual",
        column_map={
            "apn": "PropertyID",
            "owner_name": "OwnerName",
            "address_raw": "Address",
            "city": "City",
            "zip_code": "ZipCode",
            "land_value": "LandValue",
            "improvement_value": "ImprovementValue",
            "total_value": "TotalValue",
            "sqft": "SqFt",
            "year_built": "YearBuilt",
            "bedrooms": "Beds",
            "bathrooms": "Baths",
        },
        notes="Request via open-records or PTAD annual file",
    ),
    "caldwell": CadCountyConfig(
        name="Caldwell",
        fips="48055",
        cad_name="Caldwell Central Appraisal District",
        portal_url="https://caldwellcad.org",
        bulk_export_url=None,
        export_format="manual",
        column_map={
            "apn": "AccountNo",
            "owner_name": "OwnerName",
            "address_raw": "SitusAddress",
            "city": "City",
            "zip_code": "Zip",
            "land_value": "LandValue",
            "improvement_value": "ImprValue",
            "total_value": "AppraisedValue",
            "sqft": "SquareFeet",
            "year_built": "YearBuilt",
            "bedrooms": "Bedrooms",
            "bathrooms": "Bathrooms",
        },
        notes="Small county; PTAD file is most reliable source",
    ),
    "burnet": CadCountyConfig(
        name="Burnet",
        fips="48053",
        cad_name="Burnet Central Appraisal District",
        portal_url="https://burnetcad.org",
        bulk_export_url=None,
        export_format="manual",
        column_map={
            "apn": "AccountNumber",
            "owner_name": "Owner",
            "address_raw": "SitusAddress",
            "city": "City",
            "zip_code": "Zip",
            "land_value": "LandValue",
            "improvement_value": "ImprovValue",
            "total_value": "TotalValue",
            "sqft": "SqFt",
            "year_built": "YearBuilt",
            "bedrooms": "Beds",
            "bathrooms": "Baths",
        },
        notes="Request open-records; PTAD annual file available",
    ),
    "bastrop": CadCountyConfig(
        name="Bastrop",
        fips="48021",
        cad_name="Bastrop Central Appraisal District",
        portal_url="https://www.bastropcad.org",
        bulk_export_url=None,
        export_format="manual",
        column_map={
            "apn": "PropID",
            "owner_name": "OwnerName",
            "address_raw": "SitusAddress",
            "city": "SitusCity",
            "zip_code": "SitusZip",
            "land_value": "LandValue",
            "improvement_value": "ImprovValue",
            "total_value": "TotalAppr",
            "sqft": "LivingArea",
            "year_built": "YearBuilt",
            "bedrooms": "Bedrooms",
            "bathrooms": "Bathrooms",
        },
        notes="Request open-records; PTAD annual file",
    ),
    "lee": CadCountyConfig(
        name="Lee",
        fips="48287",
        cad_name="Lee Central Appraisal District",
        portal_url="https://leecad.org",
        bulk_export_url=None,
        export_format="manual",
        column_map={
            "apn": "AccountNo",
            "owner_name": "Owner",
            "address_raw": "Address",
            "city": "City",
            "zip_code": "Zip",
            "land_value": "LandValue",
            "improvement_value": "ImprovValue",
            "total_value": "TotalValue",
            "sqft": "SqFt",
            "year_built": "YrBuilt",
            "bedrooms": "Beds",
            "bathrooms": "Baths",
        },
        notes="Smallest county; PTAD file recommended",
    ),
}
