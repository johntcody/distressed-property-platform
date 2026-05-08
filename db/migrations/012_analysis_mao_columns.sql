-- Migration 012: Support MAO rows in analysis table.
-- closing_costs already exists from 004; record_type from 011.
-- MAO rows set rehab_level=NULL (not applicable), so the NOT NULL constraint is dropped.

ALTER TABLE analysis
    ADD COLUMN IF NOT EXISTS mao_version TEXT NOT NULL DEFAULT '1.0',
    ALTER COLUMN rehab_level DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analysis_mao ON analysis (property_id, record_type, mao);
