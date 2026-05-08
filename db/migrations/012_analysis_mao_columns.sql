-- Migration 012: Add mao_version to analysis; ensure closing_costs column exists.
-- record_type was added in 011 — MAO rows will use record_type = 'mao'.

ALTER TABLE analysis
    ADD COLUMN IF NOT EXISTS mao_version  TEXT NOT NULL DEFAULT '1.0',
    ADD COLUMN IF NOT EXISTS closing_costs NUMERIC(14, 2);

CREATE INDEX IF NOT EXISTS idx_analysis_mao ON analysis (property_id, record_type, mao);
