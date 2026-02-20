-- Add source column to conversation_history to track which mode produced a message.
-- NULL = normal Butler chat, 'claude_code' = Claude Code CLI mode.
ALTER TABLE butler.conversation_history
  ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT NULL;
