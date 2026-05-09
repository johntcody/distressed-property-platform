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

## Phase 6 — Security Hardening

Priority order to implement before production launch:

| # | Task | Blocks |
|---|---|---|
| 6.1 | JWT auth on all endpoints (RS256, Cognito or Auth0) | Everything — no other security control matters without this |
| 6.2 | Secrets Manager — remove all hardcoded/env creds; IAM role per service | Prevents credential leakage |
| 6.3 | Least-privilege DB users — separate `app_user` (DML only) and `migrations_user` (DDL) | Limits blast radius of SQL injection or app compromise |
| 6.4 | WAF + rate limiting — CloudFront WAF (OWASP ruleset, 100 req/IP/min) + `slowapi` in FastAPI | Required before any public traffic |
| 6.5 | VPC + security groups — RDS/OpenSearch in private subnets, SGs with least-privilege ingress | Required before production data is stored |
| 6.6 | Audit logging — CloudWatch metric filters on 401/403 spikes, RDS Performance Insights, CloudTrail | Required before investor onboarding |

## Phase 7 — Monitoring

Priority order to implement:

| # | Task | Value |
|---|---|---|
| 7.1 | CloudWatch Container Insights on ECS cluster | Immediate CPU/memory/restart visibility, one-line change |
| 7.2 | RDS Performance Insights + slow query log | Top SQL by load, free 7-day retention, zero code |
| 7.3 | SQS DLQ alarm — alert if DLQ depth > 0 | Catches silent alert engine failures (malformed messages dropped) |
| 7.4 | Custom business metrics in scrapers — events inserted per county per run | Detects silent parser failures that don't throw exceptions |
| 7.5 | Structured JSON logging (`structlog`) across all FastAPI services | Enables CloudWatch Log Insights queries for 5xx, slow paths, auth failures |
| 7.6 | Synthetic canary Lambda — poll `/health` + `/api/v1/opportunities` every 5 min | Catches routing, DNS, and cert issues that internal metrics miss |

---

## Decision Gates

These are not code tasks but must be resolved before the phases that depend on them.

| Decision | Blocks |
|---|---|
| AVM data provider (Attom, CoreLogic, Zillow) | Phase 2.2 |
| Comp data source for ARV | Phase 3.1 |
| Odyssey access strategy (scrape vs. manual) | Phase 1.5 |
| Message queue choice (SQS vs. Kafka) | ~~Phase 4.3~~ — decided: **SQS** |

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
| 4.2 — Property Detail API | **Complete** — `services/property_detail/`; GET /properties/{id}, /events, /analysis, /valuations |
| 4.3 — Alert engine | **Complete** — `services/alert_engine/`; SQS consumer, matcher, notifier stubs (email/SMS/push), daily digest; migration 013 |
| 5.1 — Investor pipeline CRUD | Not started |
| 5.2 — Frontend (Next.js) | Not started |
| 6.1 — JWT auth on all endpoints | Not started |
| 6.2 — Secrets Manager + IAM roles per service | In Progress — `services/config.py`; `infra/iam/`; update service creds + enable rotation |
| 6.3 — Least-privilege DB users | **Complete** — `db/migrations/014_least_privilege_users.sql`; verified on Neon dev DB |
| 6.4 — WAF + rate limiting | Not started |
| 6.5 — VPC + security groups | Not started |
| 6.6 — Audit logging | Not started |
| 7.1 — CloudWatch Container Insights | Not started |
| 7.2 — RDS Performance Insights + slow query log | Not started |
| 7.3 — SQS DLQ alarm | Not started |
| 7.4 — Custom business metrics in scrapers | Not started |
| 7.5 — Structured JSON logging (structlog) | Not started |
| 7.6 — Synthetic canary Lambda | Not started |


## Revised Priority Order
Phase 0  — Foundation
  + 6.3  Least-privilege DB users

Phase 1  — Data Ingestion
  + 6.2  Secrets Manager (before any Lambda is deployed)
  + 7.4  Scraper business metrics (events inserted per county)
  + 7.5  Structured logging (add structlog as each service is written)

Phase 2  — Scoring Engines
  (7.5 already in place from Phase 1)

Phase 3  — Deal Analysis
  (no change)

Phase 4  — APIs + Alerts
  + 6.1  JWT auth (build into API foundation before endpoints multiply)
  + 7.3  SQS DLQ alarm (when queue is created in 4.3)

Phase 5  — Investor Workflow + Frontend

Phase 6  — Security Hardening (remaining)
  6.4  WAF + rate limiting
  6.5  VPC + security groups
  6.6  Audit logging

Phase 7  — Monitoring (remaining)
  7.1  Container Insights
  7.2  RDS Performance Insights
  7.6  Synthetic canary
