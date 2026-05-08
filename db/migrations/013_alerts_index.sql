-- Migration 013: Additional indexes for alert engine query patterns.
-- The engine loads all active subscriptions on every event; the existing
-- partial index (WHERE active = TRUE) covers that lookup.
-- This migration adds a compound index for the digest query which joins
-- alerts → alert_subscriptions and filters by sent_at.

CREATE INDEX IF NOT EXISTS idx_alerts_subscription_sent
    ON alerts (subscription_id, sent_at DESC);
