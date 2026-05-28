-- Migration: add session_id column to tbl_conversations
-- Run this once against your PostgreSQL database.
-- Safe to run multiple times (uses IF NOT EXISTS).

ALTER TABLE tbl_conversations
  ADD COLUMN IF NOT EXISTS session_id VARCHAR(64) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_tbl_conversations_session_id
  ON tbl_conversations (session_id);

-- session_id groups turns belonging to the same chat session.
-- Used by memory_type = 'short_term' (Session mode) to load only the
-- current conversation. 'long_term' (Persistent) ignores it and loads
-- all turns for the (tenant_id, agent_id) pair. NULL = no session scoping.
COMMENT ON COLUMN tbl_conversations.session_id IS
  'Chat session identifier; scopes history for short_term/Session memory mode';
