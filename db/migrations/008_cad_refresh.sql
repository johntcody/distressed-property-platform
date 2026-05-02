-- Migration 008: Add CAD refresh tracking to properties table

ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS cad_refreshed_at TIMESTAMPTZ;

COMMENT ON COLUMN properties.cad_refreshed_at IS
    'Timestamp of last CAD bulk export upsert for this parcel';
