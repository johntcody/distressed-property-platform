-- Migration 004: Valuations and deal analysis

CREATE TYPE rehab_level AS ENUM ('light', 'medium', 'heavy');

CREATE TABLE IF NOT EXISTS valuations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    avm             NUMERIC(14, 2),
    arv             NUMERIC(14, 2),
    arv_confidence  NUMERIC(5, 2),
    comp_count      SMALLINT,
    method          TEXT,
    provider        TEXT,
    calculated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    valuation_id    UUID REFERENCES valuations (id) ON DELETE SET NULL,
    rehab_level     rehab_level NOT NULL DEFAULT 'medium',
    rehab_cost      NUMERIC(14, 2),
    rehab_cost_sqft NUMERIC(8, 2),
    arv_used        NUMERIC(14, 2),
    discount_pct    NUMERIC(5, 2) NOT NULL DEFAULT 70.0,
    holding_costs   NUMERIC(14, 2),
    closing_costs   NUMERIC(14, 2),
    mao             NUMERIC(14, 2),
    notes           TEXT,
    calculated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_valuations_property_id ON valuations (property_id);
CREATE INDEX idx_analysis_property_id   ON analysis (property_id);
