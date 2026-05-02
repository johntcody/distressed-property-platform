-- Migration 006: Investor workflow — saved properties, notes, search filters

-- ============================================================
-- SAVED_PROPERTIES
-- Investor pipeline tracking per property.
-- Status machine: new → contacted → negotiating → under_contract → closed | lost
-- ============================================================
CREATE TABLE saved_properties (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'new',    -- new | contacted | negotiating | under_contract | closed | lost
    tags        TEXT[],
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, property_id)
);

CREATE INDEX idx_saved_properties_user_id     ON saved_properties (user_id);
CREATE INDEX idx_saved_properties_status      ON saved_properties (user_id, status);

-- ============================================================
-- NOTES
-- Freeform user notes attached to a property.
-- ============================================================
CREATE TABLE notes (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    body        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notes_property ON notes (property_id, user_id);

-- ============================================================
-- SEARCH_FILTERS
-- Saved dashboard filter sets per user.
-- filters JSONB stores the full filter payload for replay.
-- ============================================================
CREATE TABLE search_filters (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    filters     JSONB NOT NULL,                 -- {county, event_types, min_distress_score, min_equity_pct, auction_date_before, ...}
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_search_filters_user_id ON search_filters (user_id);
