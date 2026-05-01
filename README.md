# Texas Distressed Property Intelligence Platform

A microservices-based platform for ingesting, scoring, and analyzing distressed real estate properties in Texas.

## Architecture Overview

- **Ingestion Pipelines** — scrapers and parsers for foreclosure, tax delinquency, probate, and pre-foreclosure data
- **Microservices** — property service, scoring engines (distress, equity, market, ARV, rehab, MAO), and alert engine
- **API Gateway** — BFF layer exposing unified REST endpoints
- **Database** — PostgreSQL with Alembic-style migrations; Elasticsearch for search indexing

## Services

| Service | Port | Description |
|---|---|---|
| api-gateway | 8000 | BFF / API Gateway |
| property-service | 8001 | Property CRUD and lookup |
| distress-score | 8002 | Distress scoring engine |
| equity-engine | 8003 | Equity calculation |
| market-score | 8004 | Market scoring |
| arv-engine | 8005 | After-repair value estimation |
| rehab-engine | 8006 | Rehab cost estimation |
| mao-engine | 8007 | Maximum allowable offer calculation |
| alert-engine | 8008 | Alert notification engine |

## Getting Started

> TODO: Add setup instructions once services are implemented.

## Docs

- [Architecture](docs/architecture.md)
- [Data Flow](docs/data-flow.md)
- [Ingestion Pipelines](docs/ingestion-pipelines.md)
- [API Spec](docs/api-spec.yaml)
