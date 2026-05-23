-- Migration: add import tracking columns to tbl_agents
-- Run this once against your PostgreSQL database.
-- Safe to run multiple times (uses IF NOT EXISTS).

ALTER TABLE tbl_agents
  ADD COLUMN IF NOT EXISTS import_source VARCHAR(20)  DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS imported_at   TIMESTAMP    DEFAULT NULL;

-- import_source values: NULL = created normally via UI
--                       'json'       = imported from .json file
--                       'zip'        = imported from .zip file
--                       'python'     = imported from .py file
--                       'javascript' = imported from .js file

COMMENT ON COLUMN tbl_agents.import_source IS
  'Source of agent creation: NULL (UI), json, zip, python, javascript';

COMMENT ON COLUMN tbl_agents.imported_at IS
  'Timestamp when agent was created via file import';
