-- Migration 003: Scores table — stores computed engine outputs

CREATE TABLE property_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    distress_score  NUMERIC(5, 2),
    market_score    NUMERIC(5, 2),
    equity_amount   NUMERIC(12, 2),
    equity_pct      NUMERIC(5, 2),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TODO: Add unique constraint on property_id (one score row per property, upsert on recompute)
-- TODO: Add index on distress_score for opportunity ranking queries
