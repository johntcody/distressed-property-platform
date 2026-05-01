-- Migration 004: Deal analysis table — ARV, rehab, MAO

CREATE TABLE deal_analysis (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id  UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    arv          NUMERIC(12, 2),
    rehab_cost   NUMERIC(12, 2),
    mao          NUMERIC(12, 2),
    rehab_level  TEXT,  -- light | moderate | heavy | full_gut
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TODO: Track comp source and comp count used for ARV
-- TODO: Add index on (property_id, computed_at DESC) for latest-analysis queries
