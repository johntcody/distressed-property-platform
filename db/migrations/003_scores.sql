-- Migration 003: Scoring outputs

CREATE TABLE IF NOT EXISTS property_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    distress_score  NUMERIC(5, 2),
    equity_amount   NUMERIC(14, 2),
    equity_pct      NUMERIC(6, 2),
    market_score    NUMERIC(5, 2),
    avm             NUMERIC(14, 2),
    estimated_liens NUMERIC(14, 2),
    tax_owed        NUMERIC(14, 2),
    score_version   TEXT NOT NULL DEFAULT '1.0',
    calculated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scores_property_id   ON property_scores (property_id);
CREATE INDEX idx_scores_distress      ON property_scores (distress_score DESC);
CREATE INDEX idx_scores_equity_pct    ON property_scores (equity_pct DESC);
CREATE INDEX idx_scores_calculated_at ON property_scores (calculated_at DESC);

CREATE VIEW latest_property_scores AS
SELECT DISTINCT ON (property_id) *
FROM property_scores
ORDER BY property_id, calculated_at DESC;
