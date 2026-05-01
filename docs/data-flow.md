# Data Flow

## Ingestion → Storage → Scoring → Alerting

```
1. Ingestion Pipeline runs on schedule (cron / event trigger)
   └─ Scraper fetches county source (HTTP)
   └─ Parser normalizes raw data into PropertyEvent
   └─ POST to property-service → stored in Postgres

2. Scoring triggered after new PropertyEvent
   └─ distress-score reads events → computes distress_score
   └─ equity-engine reads appraisal + lien data → equity_amount, equity_pct
   └─ market-score reads comp data → market_score
   └─ arv-engine reads comps → arv
   └─ rehab-engine reads condition → rehab_cost
   └─ mao-engine: mao = (arv × 0.70) − rehab_cost
   └─ All scores written back to property_scores / deal_analysis tables

3. Alert Engine polls high-score properties
   └─ Matches against active alert_subscriptions
   └─ Dispatches notifications via configured channels

4. Elasticsearch sync
   └─ Indexer subscribes to property change events
   └─ Updates ES index for fast filtered search
```

## Data Freshness

> TODO: Define SLAs for ingestion frequency per county and distress type.
