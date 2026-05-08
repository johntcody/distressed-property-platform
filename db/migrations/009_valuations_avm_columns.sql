-- Migration 009: Extend valuations table for AVM provider data

ALTER TABLE valuations
    ADD COLUMN IF NOT EXISTS confidence_score  NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS raw_response      JSONB,
    ADD COLUMN IF NOT EXISTS valuation_date    DATE;

-- Index for cache-freshness queries (WHERE property_id = $1 ORDER BY valuation_date DESC)
CREATE INDEX IF NOT EXISTS idx_valuations_property_valuation_date
    ON valuations (property_id, valuation_date DESC NULLS LAST);

COMMENT ON COLUMN valuations.confidence_score IS 'Provider confidence 0–100; NULL when not supplied';
COMMENT ON COLUMN valuations.raw_response     IS 'Full JSON response from AVM provider for auditability';
COMMENT ON COLUMN valuations.valuation_date   IS 'Date the AVM value was effective (may differ from calculated_at)';
