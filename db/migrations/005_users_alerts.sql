-- Migration 005: Users, investor pipeline, alerts, and saved searches

CREATE TYPE pipeline_status AS ENUM (
    'new',
    'contacted',
    'negotiating',
    'under_contract',
    'closed',
    'lost'
);

CREATE TYPE alert_channel AS ENUM ('email', 'sms', 'push');
CREATE TYPE alert_status  AS ENUM ('pending', 'sent', 'failed');

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT UNIQUE NOT NULL,
    full_name       TEXT,
    phone           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS saved_properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    property_id     UUID NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    status          pipeline_status NOT NULL DEFAULT 'new',
    tags            TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, property_id)
);

CREATE TABLE IF NOT EXISTS notes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    property_id     UUID NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS search_filters (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    filters         JSONB NOT NULL,                     -- stored filter criteria
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    event_id        UUID REFERENCES events (id) ON DELETE SET NULL,
    property_id     UUID REFERENCES properties (id) ON DELETE SET NULL,
    channel         alert_channel NOT NULL,
    status          alert_status NOT NULL DEFAULT 'pending',
    subject         TEXT,
    body            TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Per-user alert subscription preferences
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    event_types     distress_event_type[],              -- NULL = all types
    counties        TEXT[],                             -- NULL = all counties
    min_distress_score NUMERIC(5,2),
    channels        alert_channel[] NOT NULL DEFAULT ARRAY['email']::alert_channel[],
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_saved_properties_user     ON saved_properties (user_id);
CREATE INDEX idx_saved_properties_status   ON saved_properties (status);
CREATE INDEX idx_alerts_user_id            ON alerts (user_id);
CREATE INDEX idx_alerts_status             ON alerts (status);
CREATE INDEX idx_alert_subs_user_id        ON alert_subscriptions (user_id);

CREATE TRIGGER trg_saved_properties_updated_at
    BEFORE UPDATE ON saved_properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
