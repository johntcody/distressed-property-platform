-- Migration 005: Alerts and subscriptions

CREATE TABLE alert_subscriptions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    county              TEXT NOT NULL,
    min_distress_score  NUMERIC(5, 2) NOT NULL DEFAULT 70,
    channel             TEXT NOT NULL,  -- email | sms | webhook
    contact             TEXT NOT NULL,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties(id),
    subscription_id UUID REFERENCES alert_subscriptions(id),
    trigger_score   NUMERIC(5, 2),
    channel         TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE
);

-- TODO: Add index on (property_id, sent_at) for alert history queries
