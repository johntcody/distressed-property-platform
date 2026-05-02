-- Migration 004: Deal analysis — rehab estimates, ARV inputs, MAO

-- ============================================================
-- DEAL_ANALYSIS
-- Stores the full deal analysis snapshot: ARV, rehab, MAO.
-- Append-only so users can compare analyses over time.
-- ============================================================
CREATE TABLE deal_analysis (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id         UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,

    -- ARV inputs
    arv                 NUMERIC(12,2),
    arv_comp_count      SMALLINT,
    arv_confidence      NUMERIC(5,2),

    -- Rehab estimate
    rehab_level         TEXT NOT NULL DEFAULT 'medium', -- light | medium | heavy
    rehab_cost_per_sqft NUMERIC(7,2),
    rehab_cost_total    NUMERIC(12,2),
    rehab_overridden    BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE when user manually set cost

    -- MAO calculation
    discount_target     NUMERIC(5,2) NOT NULL DEFAULT 70.00, -- % of ARV
    holding_costs       NUMERIC(12,2) NOT NULL DEFAULT 0,
    mao                 NUMERIC(12,2),                       -- ARV * discount - rehab - holding

    -- Attribution
    computed_by         TEXT NOT NULL DEFAULT 'system',      -- system | user
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deal_analysis_property_id ON deal_analysis (property_id);
CREATE INDEX idx_deal_analysis_latest      ON deal_analysis (property_id, computed_at DESC);
