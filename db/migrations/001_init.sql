-- Migration 001: Extensions, properties, users

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- PROPERTIES
-- Core property record. All events, scores, and analysis link here.
-- APN is the universal join key to CAD data.
-- ============================================================
CREATE TABLE properties (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    apn                 TEXT,
    address_raw         TEXT NOT NULL,
    address_norm        TEXT,
    street_number       TEXT,
    street_name         TEXT,
    unit                TEXT,
    city                TEXT NOT NULL,
    county              TEXT NOT NULL,
    state               CHAR(2) NOT NULL DEFAULT 'TX',
    zip_code            VARCHAR(10) NOT NULL,
    legal_description   TEXT,
    owner_name          TEXT,
    sqft                INTEGER,
    bedrooms            SMALLINT,
    bathrooms           NUMERIC(3,1),
    year_built          SMALLINT,
    land_value          NUMERIC(12,2),
    improvement_value   NUMERIC(12,2),
    total_cad_value     NUMERIC(12,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_properties_apn
    ON properties (apn)
    WHERE apn IS NOT NULL;

CREATE INDEX idx_properties_county  ON properties (county);
CREATE INDEX idx_properties_zip     ON properties (zip_code);
CREATE INDEX idx_properties_owner   ON properties (owner_name);

-- Trigram index enables fast fuzzy address search in the dashboard
CREATE INDEX idx_properties_address_trgm
    ON properties USING GIN (address_norm gin_trgm_ops);

-- ============================================================
-- USERS
-- Platform users. Required FK target for saved_properties,
-- notes, search_filters, and alert_subscriptions.
-- ============================================================
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT,
    phone       TEXT,
    role        TEXT NOT NULL DEFAULT 'investor',
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
