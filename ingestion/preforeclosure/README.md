# Pre-Foreclosure Ingestion Pipeline

Fetches lis pendens and Notice of Default filings to identify properties entering foreclosure.

## Components

- `scraper.py` — Fetches NOD and lis pendens filings
- `parser.py` — Normalizes into structured property events
