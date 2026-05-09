-- Migration 014: Least-privilege database roles
--
-- Creates two roles:
--   app_user       — runtime role used by all FastAPI services and the SQS consumer.
--                    DML only (SELECT, INSERT, UPDATE, DELETE). No DDL.
--   migrations_user — used exclusively by the CI/CD migration runner.
--                    Full DDL rights on the app schema.
--
-- Usage:
--   Run once by a superuser (e.g. the Neon default role or RDS master user).
--   Set passwords via Secrets Manager rotation — do NOT hardcode them here.
--   After running, update each service's DATABASE_URL to use app_user credentials.
--
-- To apply passwords (run separately, not committed to source):
--   ALTER ROLE app_user       PASSWORD '<from-secrets-manager>';
--   ALTER ROLE migrations_user PASSWORD '<from-secrets-manager>';

-- ── Roles ─────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrations_user') THEN
        CREATE ROLE migrations_user LOGIN;
    END IF;
END
$$;

-- ── migrations_user — full DDL on the database ────────────────────────────────

-- Owns the schema; can CREATE, ALTER, DROP, run migrations.
-- Grant the current owner role so migrations_user can alter objects it doesn't own.
GRANT ALL PRIVILEGES ON DATABASE current_database() TO migrations_user;
GRANT ALL ON SCHEMA public TO migrations_user;

-- ── app_user — DML only ───────────────────────────────────────────────────────

-- No CREATE TABLE, no DROP, no TRUNCATE.
REVOKE ALL ON SCHEMA public FROM app_user;
GRANT USAGE ON SCHEMA public TO app_user;

-- Existing tables
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    properties,
    events,
    property_scores,
    valuations,
    analysis,
    users,
    saved_properties,
    notes,
    search_filters,
    alerts,
    alert_subscriptions
TO app_user;

-- Sequences (needed for uuid_generate_v4 fallback paths and serial columns)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user;

-- Future tables: automatically extend grants to app_user for any table created
-- by migrations_user going forward.
ALTER DEFAULT PRIVILEGES FOR ROLE migrations_user IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

ALTER DEFAULT PRIVILEGES FOR ROLE migrations_user IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO app_user;

-- ── Explicit denials (belt-and-suspenders) ────────────────────────────────────

-- app_user must never be able to drop or truncate data.
-- Postgres does not have a DENY syntax; instead we rely on not granting
-- these privileges above. This comment documents the intent explicitly.
--
-- app_user cannot:
--   DROP TABLE, ALTER TABLE, TRUNCATE, CREATE INDEX, CREATE EXTENSION
--   Access pg_shadow, pg_authid, or any system catalog requiring superuser
