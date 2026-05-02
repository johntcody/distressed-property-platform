-- Migration 005: Alert subscriptions and dispatched alerts

-- ============================================================
-- ALERT_SUBSCRIPTIONS
-- Per-user filter rules. An alert fires when an incoming event
-- matches the user's county, event type, and score threshold.
-- ============================================================
CREATE TABLE alert_subscriptions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    county              TEXT,                   -- NULL = all counties
    event_types         TEXT[],                 -- NULL = all types; e.g. {foreclosure, probate}
    min_distress_score  NUMERIC(5,2),           -- NULL = no threshold
    min_equity_pct      NUMERIC(5,2),           -- NULL = no threshold
    channel             TEXT NOT NULL,          -- email | sms | push
    contact             TEXT NOT NULL,          -- email address, phone, or push token
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_subs_user_id ON alert_subscriptions (user_id);
CREATE INDEX idx_alert_subs_active  ON alert_subscriptions (active) WHERE active = TRUE;

-- ============================================================
-- ALERTS
-- Record of every dispatched notification.
-- ============================================================
CREATE TABLE alerts (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id      UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    subscription_id  UUID REFERENCES alert_subscriptions(id) ON DELETE SET NULL,
    event_id         UUID REFERENCES events(id) ON DELETE SET NULL,
    trigger_type     TEXT NOT NULL,             -- event_type that fired this alert
    trigger_score    NUMERIC(5,2),
    channel          TEXT NOT NULL,
    contact          TEXT NOT NULL,
    sent_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged     BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at  TIMESTAMPTZ
);

CREATE INDEX idx_alerts_property_id ON alerts (property_id);
CREATE INDEX idx_alerts_sent_at     ON alerts (sent_at DESC);
CREATE INDEX idx_alerts_user        ON alerts (subscription_id);
