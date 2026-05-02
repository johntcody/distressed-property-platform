# Database ERD — Texas Distressed Property Intelligence Platform

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USERS                                       │
│  id (PK) · email · full_name · phone · role · active                   │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │ 1
          ┌─────────────┼──────────────────────┐
          │ N           │ N                    │ N
          ▼             ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
│ SAVED_PROPERTIES │  │     NOTES        │  │   SEARCH_FILTERS     │
│ id               │  │ id               │  │ id                   │
│ user_id (FK)     │  │ user_id (FK)     │  │ user_id (FK)         │
│ property_id (FK) │  │ property_id (FK) │  │ name                 │
│ status           │  │ body             │  │ filters (JSONB)      │
│ tags[]           │  └──────────────────┘  └──────────────────────┘
└──────────────────┘
          │
          │                  ┌──────────────────────────────────────┐
          │                  │          ALERT_SUBSCRIPTIONS         │
          │                  │ id · user_id (FK) · county           │
          │                  │ event_types[] · min_distress_score   │
          │                  │ min_equity_pct · channel · contact   │
          │                  └──────────────────┬───────────────────┘
          │                                     │ 1
          │                                     │ N
          │                                     ▼
          │                            ┌────────────────┐
          │                            │    ALERTS      │
          │                            │ id             │
          │                            │ property_id FK │
          │                            │ sub_id FK      │
          │                            │ event_id FK    │
          │                            │ channel        │
          │                            │ sent_at        │
          │                            └───────┬────────┘
          │                                    │
          └─────────────────┐                  │
                            ▼                  │
┌───────────────────────────────────────────────────────────────────────┐
│                          PROPERTIES                                    │
│  id (PK) · apn · address_raw · address_norm · city · county          │
│  state · zip_code · owner_name · sqft · bedrooms · bathrooms         │
│  year_built · land_value · improvement_value · total_cad_value       │
└───┬─────────────┬──────────────┬────────────────┬─────────────────────┘
    │             │              │                │
    │ 1           │ 1            │ 1              │ 1
    │ N           │ 1            │ N              │ N
    ▼             ▼              ▼                ▼
┌─────────┐  ┌────────────────┐  ┌───────────┐  ┌──────────────┐
│ EVENTS  │  │ PROPERTY_SCORES│  │VALUATIONS │  │ DEAL_ANALYSIS│
│ id      │  │ id             │  │ id        │  │ id           │
│ prop_id │  │ property_id    │  │ prop_id   │  │ prop_id      │
│ type    │  │ (UNIQUE)       │  │ type      │  │ arv          │
│ county  │  │ distress_score │  │ value     │  │ rehab_cost   │
│ borrower│  │ avm            │  │ confidence│  │ mao          │
│ lender  │  │ equity_amount  │  │ comp_count│  │ rehab_level  │
│ trustee │  │ equity_pct     │  │ source    │  │ discount_pct │
│ auction │  │ market_score   │  └───────────┘  │ holding_costs│
│ case_no │  │ computed_at    │                 └──────────────┘
│ tax_owed│  └────────────────┘
│ raw_data│
└─────────┘

Legend:
  FK  = Foreign key
  PK  = Primary key
  1   = one side of relationship
  N   = many side of relationship
  UNIQUE on property_scores.property_id → upsert-safe score storage
```

## Migration Execution Order

```
001_init.sql        -- properties, users
002_events.sql      -- events (depends on properties)
003_scores.sql      -- property_scores, valuations (depends on properties)
004_analysis.sql    -- deal_analysis (depends on properties)
005_alerts.sql      -- alert_subscriptions (depends on users), alerts (depends on properties, events)
006_workflow.sql    -- saved_properties, notes, search_filters (depends on users + properties)
007_triggers.sql    -- updated_at triggers (depends on all tables)
```
