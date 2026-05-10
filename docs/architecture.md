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
| Database | PostgreSQL (RDS) |
| Search | OpenSearch |
| Ingestion | Python (httpx, BeautifulSoup) — Lambda |
| API Gateway | FastAPI + CloudFront + WAF |
| Frontend | Next.js (placeholder) |

---

## Network Architecture (Phase 6.5)

All data-tier infrastructure runs in private subnets with no public endpoints.
ECS tasks reach external APIs (county sites, Estated, SQS) via NAT Gateway.

```
Internet
    │
    ▼
┌────────────────────────────────────────────────────────┐
│  CloudFront  +  WAF WebACL                             │
│  (geo-block non-US, OWASP CRS, SQLi, rate limit)       │
└────────────────────────┬───────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼───────────────────────────────┐
│              PUBLIC SUBNETS (AZ-1 / AZ-2)              │
│                                                        │
│  ┌─────────────┐      ┌──────────────────────────┐     │
│  │  ALB        │      │  NAT Gateway (AZ-1)      │     │
│  │  SG: 443/80 │      │  (ECS → internet egress) │     │
│  │  from 0/0   │      └──────────────────────────┘     │
│  └──────┬──────┘                                       │
└─────────│──────────────────────────────────────────────┘
          │ 443/80 from ALB SG only
┌─────────│──────────────────────────────────────────────┐
│         ▼      PRIVATE SUBNETS (AZ-1 / AZ-2)          │
│                                                        │
│  ┌───────────────────────────────────────────────┐     │
│  │  ECS Tasks (FastAPI microservices)            │     │
│  │  SG: inbound 443/80 from ALB SG               │     │
│  │      outbound unrestricted (via NAT)          │     │
│  └───────┬──────────────────────┬────────────────┘     │
│          │ 5432                 │ 443                   │
│  ┌───────▼──────┐   ┌───────────▼──────────────┐       │
│  │  RDS         │   │  OpenSearch              │       │
│  │  Postgres    │   │  Domain (VPC mode)       │       │
│  │  SG: 5432    │   │  SG: 443 from ECS SG     │       │
│  │  from ECS +  │   │  only; no public         │       │
│  │  Lambda SG   │   │  endpoint                │       │
│  └──────────────┘   └──────────────────────────┘       │
│                                                        │
│  ┌───────────────────────────────────────────────┐     │
│  │  Lambda Scrapers                              │     │
│  │  SG: no inbound; outbound unrestricted        │     │
│  │  (county clerk sites, CAD APIs, Estated)      │     │
│  └───────┬───────────────────────────────────────┘     │
│          │ 5432 to RDS SG                              │
└──────────│─────────────────────────────────────────────┘
           │
           ▼  (via NAT Gateway → Internet)
    County clerk sites, Estated AVM, SQS, Secrets Manager
```

### Security Group Rules Summary

| SG | Inbound | Outbound |
|---|---|---|
| ALB SG | 443, 80 from `0.0.0.0/0` | 443, 80 to ECS SG only |
| ECS SG | 443, 80 from ALB SG | All unrestricted (via NAT) |
| RDS SG | 5432 from ECS SG + Lambda SG | All protocols to VPC CIDR only |
| OpenSearch SG | 443 from ECS SG | All |
| Lambda SG | None | All unrestricted (via NAT) |

### VPC Flow Logs
- All VPC traffic logged to CloudWatch `/dpip/vpc/flow-logs-<env>` (30-day retention)
- CloudWatch metric filter + alarm triggers on REJECT records from either private subnet prefix (`10.0.10.*` / `10.0.11.*`) — covers all workloads in the shared private subnets (ECS, RDS, OpenSearch, Lambda)
