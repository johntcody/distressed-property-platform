# Implementation Priority Order

## Phase 0 — Foundation

| # | Task | Why |
|---|---|---|
| 0.1 | Database schema + migrations | All services write to Postgres; nothing works without tables |
| 0.2 | Repo scaffolding | Establishes module boundaries before any code is written |
| 0.3 | CAD data ingestion | APN is the universal join key — without it, no matching works |

## Phase 1 — Data Ingestion

| # | Task | Why |
|---|---|---|
| 1.1 | Foreclosure scraper (County Clerk PDFs) | Highest investor value; earliest distress signal |
| 1.2 | Property normalization + APN matching | Required to make any event record useful |
| 1.3 | Tax delinquency scraper | Second-highest signal; monthly cadence = lower urgency |
| 1.4 | Pre-foreclosure / Lis Pendens scraper | Pairs with foreclosure for full pre→post pipeline |
| 1.5 | Probate scraper | Highest technical risk (Odyssey); build last in this group |

## Phase 2 — Scoring Engines

| # | Task | Why |
|---|---|---|
| 2.1 | Distress score engine | Drives dashboard filtering; unblocks Phase 3 |
| 2.2 | Equity estimation engine | Second-most used filter; needs AVM stub decision made |
| 2.3 | Market score engine | Monthly cadence; least urgent of the three |

## Phase 3 — Deal Analysis

| # | Task | Why |
|---|---|---|
| 3.1 | ARV calculator | Feeds MAO; needs comp data source decided |
| 3.2 | Rehab cost estimator | Simple templates; low risk, high usability |
| 3.3 | MAO calculator | Last in chain; depends on ARV + rehab |

## Phase 4 — APIs + Alerts

| # | Task | Why |
|---|---|---|
| 4.1 | Opportunity Dashboard API | First thing the frontend needs |
| 4.2 | Property Detail API | Second frontend dependency |
| 4.3 | Alert engine | Requires scoring to be stable before alerts are meaningful |

## Phase 5 — Investor Workflow + Frontend

| # | Task | Why |
|---|---|---|
| 5.1 | Save/track pipeline (CRUD) | Simple but depends on auth/users table |
| 5.2 | Frontend (Next.js) | Build last; all APIs must be stable |

---

## Decision Gates

These are not code tasks but must be resolved before the phases that depend on them.

| Decision | Blocks |
|---|---|
| AVM data provider (Attom, CoreLogic, Zillow) | Phase 2.2 |
| Comp data source for ARV | Phase 3.1 |
| Odyssey access strategy (scrape vs. manual) | Phase 1.5 |
| Message queue choice (SQS vs. Kafka) | Phase 4.3 |

---

## Status

| Phase | Status |
|---|---|
| 0.1 — Database schema | Complete — `db/migrations/001–005` |
| 0.2 — Repo scaffolding | Complete |
| 0.3 — CAD data ingestion | Complete |
| 1.1 — Foreclosure scraper | **Complete** — `ingestion/foreclosure/` |
| 1.2 — Property normalization | **Complete** — `services/property-service/normalizer.py` |
| 1.3 — Tax delinquency scraper | **Complete** — `ingestion/tax_delinquency/` |
| 1.4 — Pre-foreclosure scraper | **Complete** — `ingestion/preforeclosure/` |
| 1.5 — Probate scraper | **Complete** — `ingestion/probate/` (Burnet + Lee = manual fallback) |
| 2.1 — Distress score engine | **Complete** — `services/distress-score/` |
| 2.2 — Equity estimation engine | **Complete** — `services/equity_engine/` |
| 2.2.1 — AVM service (Estated) | **Complete** — `services/avm_service/`; equity engine reads `valuations` with CAD fallback |
| 2.3 — Market score engine | **Complete** — `services/market_score/` |
| 3.1 — ARV calculator | **Complete** — `services/arv_engine/`; stub comp provider; inverse-distance-weighted price/sqft |
| 3.2 — Rehab cost estimator | **Complete** — `services/rehab_engine/`; 3 templates (light/medium/heavy), per-item overrides |
| 3.3 — MAO calculator | **Complete** — `services/mao_engine/`; formula MAO=(ARV×discount%)−rehab−holding−closing; ARV+rehab pulled from DB |
| 4.1 — Opportunity Dashboard API | **Complete** — `services/opportunity_dashboard/`; GET /api/v1/opportunities; 5 filters, 5 sort fields, pagination |
| 4.2 — Property Detail API | Not started |
| 4.3 — Alert engine | Not started |
| 5.1 — Investor pipeline CRUD | Not started |
| 5.2 — Frontend (Next.js) | Not started |
