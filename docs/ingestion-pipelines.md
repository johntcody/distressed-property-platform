# Ingestion Pipelines

## Pipelines

| Pipeline | Source Type | Frequency | Counties Covered |
|---|---|---|---|
| foreclosure | County courthouse / trustee sale | Weekly | Harris, Dallas, Bexar, Travis |
| tax_delinquency | County appraisal district (CAD) | Monthly | All target counties |
| probate | County clerk portal | Weekly | Harris, Dallas |
| preforeclosure | District court lis pendens | Weekly | Harris, Dallas, Bexar |

## Pipeline Lifecycle

1. **Fetch** — HTTP scraper retrieves raw HTML or JSON from source
2. **Parse** — Parser extracts structured fields (address, dates, case numbers)
3. **Deduplicate** — Match against existing records via parcel ID or address hash
4. **Persist** — Write `PropertyEvent` to Postgres via `property-service`
5. **Trigger scoring** — Emit event to kick off scoring pipeline

## Adding a New County

> TODO: Document per-county configuration pattern.
