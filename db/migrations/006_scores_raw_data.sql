-- Migration 006: Add raw_data column to property_scores
--
-- Databases that applied 003_scores.sql before Phase 2.1 do not have this
-- column. Using ALTER TABLE instead of editing the historical migration ensures
-- existing deployed schemas are updated safely.

ALTER TABLE property_scores
    ADD COLUMN IF NOT EXISTS raw_data JSONB;  -- per-component score breakdown
