# CAD Data Ingestion — Phase 0.3

Loads Central Appraisal District (CAD) bulk export files for all 7 target Texas counties
and upserts property records into the `properties` table. APN is the universal join key
used by every downstream service.

## County Data Sources

| County | CAD Entity | Bulk Export | Format |
|---|---|---|---|
| Hays | Hays CAD | Open-records request / PTAD | CSV |
| Travis | Travis CAD | Portal download + PTAD | CSV |
| Williamson | Williamson CAD | Open-records request / PTAD | CSV |
| Caldwell | Caldwell CAD | PTAD annual file | CSV |
| Burnet | Burnet CAD | PTAD annual file | CSV |
| Bastrop | Bastrop CAD | PTAD annual file | CSV |
| Lee | Lee CAD | PTAD annual file | CSV |

**PTAD** (Property Tax Assistance Division) publishes annual certified appraisal roll files
for every Texas county at no cost: https://comptroller.texas.gov/taxes/property-tax/

## Quick Start

```bash
# Install dependencies
pip install psycopg2-binary openpyxl

# Set connection string
export DATABASE_URL="postgresql://dp_db_admin:PASSWORD@127.0.0.1:5433/distressed_property_db"

# Run against a county export file
python -m ingestion.cad.runner --county travis --file /data/travis_cad_2024.csv
```

## File Structure

```
ingestion/cad/
├── __init__.py
├── counties.py   # Per-county configs and column mappings
├── loader.py     # CSV / XLSX parser → normalized dicts
├── writer.py     # Postgres upsert logic (batch-safe)
└── runner.py     # CLI entry point / Lambda handler
```

## Running Tests

```bash
pytest tests/ingestion/cad/
```

## Scheduling

The runner exposes a Lambda-compatible `handler(event, context)` function.
Only local filesystem paths are supported — download the file to `/tmp` before invoking:

```python
# In your Lambda function:
s3.download_file("my-bucket", "travis_2024.csv", "/tmp/travis_2024.csv")
handler({"county": "travis", "file": "/tmp/travis_2024.csv"}, None)
```

Recommended cadence: **weekly** (CAD values change at annual re-appraisal; weekly catches
mid-year corrections and ownership transfers).
