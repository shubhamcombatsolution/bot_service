-- Migration: add memory_mode column to tbl_custombot_new
-- Run this once against your PostgreSQL database.
-- Safe to run multiple times (uses IF NOT EXISTS).

ALTER TABLE tbl_custombot_new
  ADD COLUMN IF NOT EXISTS memory_mode VARCHAR(30) DEFAULT NULL;

-- memory_mode controls how the bot remembers conversation turns:
--   'structured'  = no memory between messages
--   'session'     = remembers within a conversation (scoped by session_id)
--   'persistent'  = long-term memory across sessions
-- NULL is treated as 'session' (preserves prior runtime behavior).
COMMENT ON COLUMN tbl_custombot_new.memory_mode IS
  'Conversation memory behavior: structured | session | persistent (NULL = session)';
