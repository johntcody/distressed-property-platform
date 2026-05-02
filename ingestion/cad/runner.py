"""
CAD ingestion runner — entry point for scheduled execution.

Usage (manual):
    python -m ingestion.cad.runner --county travis --file /data/travis_cad_2024.csv

Usage (Lambda / cron pattern):
    handler(event={"county": "travis", "file": "s3://bucket/travis_cad_2024.csv"}, context=None)

Environment variables:
    DATABASE_URL   — psycopg2 DSN, e.g. postgresql://user:pass@host:5433/dbname
"""

import argparse
import logging
import os
import sys

import psycopg2

from ingestion.cad.counties import COUNTY_CONFIGS
from ingestion.cad.loader import load_cad_file
from ingestion.cad.writer import upsert_parcels_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run(county: str, file_path: str) -> dict:
    config = COUNTY_CONFIGS.get(county.lower())
    if config is None:
        raise ValueError(f"Unknown county: {county!r}. Valid: {list(COUNTY_CONFIGS)}")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    logger.info("Starting CAD ingestion — county=%s file=%s", county, file_path)

    conn = psycopg2.connect(dsn)
    try:
        parcels = load_cad_file(config, file_path)
        result = upsert_parcels_batch(conn, parcels)
    finally:
        conn.close()

    logger.info(
        "CAD ingestion complete — county=%s inserted=%d updated=%d errors=%d",
        county, result["inserted"], result["updated"], result["errors"],
    )
    return result


def handler(event: dict, context) -> dict:
    """AWS Lambda / Lambda-style entry point."""
    county = event.get("county")
    file_path = event.get("file")
    if not county or not file_path:
        raise ValueError("Event must contain 'county' and 'file' keys")
    return run(county, file_path)


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Ingest CAD bulk export into properties table")
    parser.add_argument("--county", required=True, choices=list(COUNTY_CONFIGS), help="County name")
    parser.add_argument("--file", required=True, help="Path to CAD export file (CSV or XLSX)")
    args = parser.parse_args()

    try:
        result = run(args.county, args.file)
        sys.exit(0 if result["errors"] == 0 else 1)
    except Exception as exc:
        logger.error("Fatal: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
