-- Migration 003: Scores and valuations

-- ============================================================
-- PROPERTY_SCORES
-- One row per property. Upsert on recompute using ON CONFLICT (property_id).
-- Stores distress, equity, and market score outputs together
-- since they are always consumed together on the dashboard.
-- ============================================================
CREATE TABLE property_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL UNIQUE REFERENCES properties(id) ON DELETE CASCADE,

    -- Distress score engine outputs
    distress_score  NUMERIC(5,2),               -- 0–100
    distress_factors JSONB,                     -- breakdown: {foreclosure_stage, tax_years, probate, lp_recency}

    -- Equity engine outputs
    avm             NUMERIC(12,2),              -- automated valuation from external provider
    estimated_loan_balance NUMERIC(12,2),
    tax_owed        NUMERIC(12,2),
    equity_amount   NUMERIC(12,2),              -- AVM - liens - taxes
    equity_pct      NUMERIC(5,2),               -- equity_amount / AVM * 100

    -- Market score engine outputs
    market_score    NUMERIC(5,2),               -- 0–100
    appreciation_rate NUMERIC(5,2),             -- YoY %
    avg_days_on_market SMALLINT,
    rent_to_price_ratio NUMERIC(6,4),

    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_property_scores_distress ON property_scores (distress_score DESC);
CREATE INDEX idx_property_scores_equity   ON property_scores (equity_pct DESC);
CREATE INDEX idx_property_scores_market   ON property_scores (market_score DESC);

-- ============================================================
-- VALUATIONS
-- Append-only history of ARV and AVM calculations.
-- property_scores holds the latest; this table holds the audit trail.
-- ============================================================
CREATE TABLE valuations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    valuation_type  TEXT NOT NULL,              -- ARV | AVM
    value           NUMERIC(12,2) NOT NULL,
    confidence_score NUMERIC(5,2),             -- 0–100; populated for ARV
    comp_count      SMALLINT,                  -- number of comps used for ARV
    comp_radius_miles NUMERIC(4,2),
    source          TEXT,                      -- provider name for AVM
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_valuations_property_id ON valuations (property_id);
CREATE INDEX idx_valuations_type_date   ON valuations (property_id, valuation_type, computed_at DESC);
