-- Migration 001: Core property records
-- Canonical property entity — all events, scores, and valuations link here

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;  -- for lat/lon point queries

CREATE TABLE IF NOT EXISTS properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apn             TEXT UNIQUE,                        -- assessor parcel number (join key)
    address         TEXT NOT NULL,
    address_norm    TEXT,                               -- USPS-normalized form
    city            TEXT NOT NULL,
    county          TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'TX',
    zip_code        TEXT,
    lat             NUMERIC(10, 7),
    lon             NUMERIC(10, 7),
    owner_name      TEXT,
    sqft            INTEGER,
    beds            SMALLINT,
    baths           NUMERIC(3,1),
    year_built      SMALLINT,
    land_value      NUMERIC(14, 2),
    improvement_value NUMERIC(14, 2),
    legal_description TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ                         -- soft-delete; NULL = active
);

CREATE INDEX idx_properties_county  ON properties (county);
CREATE INDEX idx_properties_apn     ON properties (apn);
CREATE INDEX idx_properties_zip     ON properties (zip_code);
CREATE INDEX idx_properties_owner   ON properties (owner_name);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_properties_updated_at
    BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
