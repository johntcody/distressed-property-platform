-- Migration 002: Property events table

CREATE TABLE property_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    source      TEXT NOT NULL,
    county      TEXT NOT NULL,
    raw_data    JSONB,
    occurred_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TODO: Add index on (property_id, event_type)
-- TODO: Add index on ingested_at for pipeline monitoring queries
