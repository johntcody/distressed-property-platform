-- Migration 011: Add record_type to analysis for explicit rehab vs MAO isolation
-- Existing rows get 'rehab' as the default since that was the only writer so far.
ALTER TABLE analysis
    ADD COLUMN IF NOT EXISTS record_type TEXT NOT NULL DEFAULT 'rehab';

CREATE INDEX IF NOT EXISTS idx_analysis_record_type ON analysis (property_id, record_type);
