-- Migration 002: Distress events
-- One row per filing/posting; multiple events can link to the same property

CREATE TYPE distress_event_type AS ENUM (
    'foreclosure',
    'tax_delinquency',
    'probate',
    'preforeclosure'
);

CREATE TYPE foreclosure_stage AS ENUM (
    'NOD',
    'NTS',
    'auction',
    'REO'
);

CREATE TABLE IF NOT EXISTS events (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id          UUID REFERENCES properties (id) ON DELETE SET NULL,
    event_type           distress_event_type NOT NULL,
    county               TEXT NOT NULL,
    filing_date          DATE,
    auction_date         DATE,
    foreclosure_stage    foreclosure_stage,
    borrower_name        TEXT,
    lender_name          TEXT,
    trustee_name         TEXT,
    loan_amount          NUMERIC(14, 2),
    tax_amount_owed      NUMERIC(14, 2),
    years_delinquent     SMALLINT,
    case_number          TEXT,
    decedent_name        TEXT,
    executor_name        TEXT,
    lp_instrument_number TEXT,
    lp_keywords          TEXT[],
    legal_description    TEXT,
    source_url           TEXT,
    raw_data             JSONB,
    dedup_key            TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Partial unique index: enforces dedup only when dedup_key is present.
-- Standard UNIQUE allows multiple NULLs in Postgres, which silently breaks
-- deduplication for events where key fields are missing from the source.
CREATE UNIQUE INDEX idx_events_dedup_key ON events (dedup_key) WHERE dedup_key IS NOT NULL;

CREATE INDEX idx_events_property_id  ON events (property_id);
CREATE INDEX idx_events_event_type   ON events (event_type);
CREATE INDEX idx_events_county       ON events (county);
CREATE INDEX idx_events_filing_date  ON events (filing_date DESC);
CREATE INDEX idx_events_auction_date ON events (auction_date);
