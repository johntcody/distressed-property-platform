-- Migration 001: Initial schema — properties table

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE properties (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    address       TEXT NOT NULL,
    city          TEXT NOT NULL,
    county        TEXT NOT NULL,
    state         CHAR(2) NOT NULL DEFAULT 'TX',
    zip_code      VARCHAR(10) NOT NULL,
    parcel_id     TEXT,
    owner_name    TEXT,
    distress_type TEXT NOT NULL,  -- foreclosure | tax_delinquency | probate | preforeclosure
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- TODO: Add unique constraint on (parcel_id) once deduplication logic is ready
-- TODO: Add GIN index on address for fuzzy search
