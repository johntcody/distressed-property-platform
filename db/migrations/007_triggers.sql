-- Migration 007: updated_at auto-maintenance trigger

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_properties_updated_at
    BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_alert_subs_updated_at
    BEFORE UPDATE ON alert_subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_saved_properties_updated_at
    BEFORE UPDATE ON saved_properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_notes_updated_at
    BEFORE UPDATE ON notes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
