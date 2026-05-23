-- Migration: Add import tracking columns to tbl_agents
-- Run this once against your PostgreSQL database.
-- Safe to run multiple times (uses IF NOT EXISTS).

ALTER TABLE tbl_agents
  ADD COLUMN IF NOT EXISTS import_source VARCHAR(20)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS imported_at   TIMESTAMP    DEFAULT NULL;

-- import_source values:
--   NULL        → agent was created manually via the UI
--   'json'      → created from agent.json upload
--   'zip'       → created from agent.zip upload
--   'python'    → created from .py file upload
--   'javascript'→ created from .js file upload

COMMENT ON COLUMN tbl_agents.import_source IS 'File type used to import this agent: json | zip | python | javascript | NULL (manual)';
COMMENT ON COLUMN tbl_agents.imported_at   IS 'Timestamp when the agent was created via file import';
