-- Migration 010: Add arv_version to valuations for round-trip fidelity on GET
ALTER TABLE valuations
    ADD COLUMN IF NOT EXISTS arv_version TEXT NOT NULL DEFAULT '1.0';
