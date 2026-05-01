# Architecture

## Overview

The Texas Distressed Property Intelligence Platform is a microservices system for ingesting, enriching, scoring, and surfacing distressed real estate investment opportunities across Texas counties.

## Component Diagram

```
┌──────────────────────────────────────────────────────┐
│                  Ingestion Layer                     │
│  foreclosure | tax_delinquency | probate | prefc.    │
└──────────────────────┬───────────────────────────────┘
                       │ property events
┌──────────────────────▼───────────────────────────────┐
│             property-service (Postgres)              │
└──────┬───────────────┬────────────────┬──────────────┘
       │               │                │
┌──────▼──┐    ┌───────▼────┐   ┌───────▼──────┐
│distress │    │equity      │   │market-score  │
│-score   │    │-engine     │   │              │
└──────┬──┘    └───────┬────┘   └───────┬──────┘
       │               │                │
       └───────────────▼────────────────┘
                ┌──────────────┐
                │  arv-engine  │
                │  rehab-engine│
                │  mao-engine  │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │ alert-engine │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │ API Gateway  │
                │    (BFF)     │
                └──────────────┘
```

## Technology Stack

| Layer | Technology |
|---|---|
| Services | Python / FastAPI |
| Database | PostgreSQL |
| Search | Elasticsearch |
| Ingestion | Python (httpx, BeautifulSoup) |
| API Gateway | FastAPI |
| Frontend | Next.js (placeholder) |
