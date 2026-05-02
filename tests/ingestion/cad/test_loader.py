"""Unit tests for CAD file loader — no database required."""

import csv
import io
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion.cad.counties import COUNTY_CONFIGS
from ingestion.cad.loader import load_cad_file, _to_int, _to_float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(tmp_path: Path, county: str, rows: list[dict]) -> Path:
    config = COUNTY_CONFIGS[county]
    headers = list(config.column_map.values())
    file = tmp_path / f"{county}_cad.csv"
    with open(file, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    return file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_travis_csv(tmp_path):
    config = COUNTY_CONFIGS["travis"]
    cm = config.column_map

    rows = [
        {
            cm["apn"]: "123456",
            cm["owner_name"]: "SMITH JOHN",
            cm["address_raw"]: "123 MAIN ST",
            cm["city"]: "AUSTIN",
            cm["zip_code"]: "78701",
            cm["land_value"]: "50000",
            cm["improvement_value"]: "150000",
            cm["total_value"]: "200000",
            cm["sqft"]: "1800",
            cm["year_built"]: "1995",
            cm["bedrooms"]: "3",
            cm["bathrooms"]: "2",
        }
    ]
    file = _write_csv(tmp_path, "travis", rows)
    parcels = list(load_cad_file(config, file))

    assert len(parcels) == 1
    p = parcels[0]
    assert p["apn"] == "123456"
    assert p["county"] == "travis"
    assert p["state"] == "TX"
    assert p["owner_name"] == "SMITH JOHN"
    assert p["total_cad_value"] == 200000.0
    assert p["sqft"] == 1800
    assert p["year_built"] == 1995


def test_row_without_apn_is_skipped(tmp_path):
    config = COUNTY_CONFIGS["travis"]
    cm = config.column_map
    rows = [
        {
            cm["apn"]: "",          # empty APN
            cm["owner_name"]: "TEST",
            cm["address_raw"]: "1 TEST ST",
            cm["city"]: "AUSTIN",
            cm["zip_code"]: "78701",
            cm["land_value"]: "0",
            cm["improvement_value"]: "0",
            cm["total_value"]: "0",
            cm["sqft"]: "0",
            cm["year_built"]: "2000",
            cm["bedrooms"]: "2",
            cm["bathrooms"]: "1",
        }
    ]
    file = _write_csv(tmp_path, "travis", rows)
    parcels = list(load_cad_file(config, file))
    assert parcels == []


def test_all_counties_have_required_keys():
    required = {"apn", "owner_name", "address_raw", "city", "zip_code",
                "land_value", "improvement_value", "total_value"}
    for name, config in COUNTY_CONFIGS.items():
        missing = required - set(config.column_map.keys())
        assert not missing, f"{name} missing column_map keys: {missing}"


def test_to_float_handles_commas():
    assert _to_float("1,250,000") == 1250000.0
    assert _to_float("") is None
    assert _to_float(None) is None


def test_to_int_handles_bad_value():
    assert _to_int("abc") is None
    assert _to_int("42") == 42
    assert _to_int(None) is None
    assert _to_int("1,800") == 1800     # comma-separated
    assert _to_int("1800.0") == 1800    # Excel float representation
    assert _to_int("") is None


def test_bathrooms_parses_as_float(tmp_path):
    """bathrooms is NUMERIC(3,1) — fractional values like 2.5 must not be dropped."""
    config = COUNTY_CONFIGS["travis"]
    cm = config.column_map

    def _make_row(baths: str) -> dict:
        return {
            cm["apn"]: "999",
            cm["owner_name"]: "TEST",
            cm["address_raw"]: "1 TEST ST",
            cm["city"]: "AUSTIN",
            cm["zip_code"]: "78701",
            cm["land_value"]: "0",
            cm["improvement_value"]: "0",
            cm["total_value"]: "0",
            cm["sqft"]: "0",
            cm["year_built"]: "2000",
            cm["bedrooms"]: "3",
            cm["bathrooms"]: baths,
        }

    for baths_str, expected in [("2.5", 2.5), ("3.0", 3.0), ("2", 2.0)]:
        file = _write_csv(tmp_path / baths_str, "travis", [_make_row(baths_str)])
        parcels = list(load_cad_file(config, file))
        assert parcels[0]["bathrooms"] == expected, f"Failed for bathrooms={baths_str!r}"
