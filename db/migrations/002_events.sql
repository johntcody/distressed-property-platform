-- Migration 002: Events table
-- Stores all distress signals ingested from county sources.
-- Uses typed columns for filterable fields + raw_data JSONB for source fidelity.

CREATE TABLE events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id         UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    event_type          TEXT NOT NULL,          -- foreclosure | tax_delinquency | probate | preforeclosure
    county              TEXT NOT NULL,
    source_url          TEXT,
    source_file         TEXT,

    -- Foreclosure fields
    borrower_name       TEXT,
    lender_name         TEXT,
    trustee_name        TEXT,
    auction_date        DATE,
    foreclosure_stage   TEXT,                   -- NOD | NTS | auction

    -- Tax delinquency fields
    tax_amount_owed     NUMERIC(12,2),
    tax_years_delinquent SMALLINT,

    -- Probate fields
    case_number         TEXT,
    decedent_name       TEXT,
    executor_name       TEXT,

    -- Pre-foreclosure / Lis Pendens fields
    filing_type         TEXT,                   -- lis_pendens | default | other
    filing_date         DATE,
    plaintiff_name      TEXT,
    defendant_name      TEXT,

    -- Source preservation
    raw_data            JSONB,

    occurred_at         TIMESTAMPTZ,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_property_id   ON events (property_id);
CREATE INDEX idx_events_event_type    ON events (event_type);
CREATE INDEX idx_events_county        ON events (county);
CREATE INDEX idx_events_auction_date  ON events (auction_date) WHERE auction_date IS NOT NULL;
CREATE INDEX idx_events_filing_date   ON events (filing_date)  WHERE filing_date IS NOT NULL;
CREATE INDEX idx_events_ingested_at   ON events (ingested_at);

-- Prevent duplicate ingestion: same property, same type, same source file
CREATE UNIQUE INDEX uq_events_dedup
    ON events (property_id, event_type, source_file)
    WHERE source_file IS NOT NULL;
