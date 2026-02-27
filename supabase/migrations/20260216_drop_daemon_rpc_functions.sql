-- =============================================================================
-- Drop Daemon RPC Functions
-- =============================================================================
-- These SECURITY DEFINER functions are no longer needed since the backend
-- now uses sb_secret_ key which bypasses RLS directly.
--
-- The secret key approach is simpler and more secure because:
-- 1. No need for complex RPC functions
-- 2. Direct table access is easier to debug
-- 3. The key can be rotated independently
-- 4. No risk of SQL injection through RPC parameters
-- =============================================================================

-- Drop the functions
DROP FUNCTION IF EXISTS daemon_get_task(UUID);
DROP FUNCTION IF EXISTS daemon_update_task_status(UUID, TEXT, TEXT, TEXT, INTEGER);
DROP FUNCTION IF EXISTS daemon_list_pending_tasks(TEXT);
DROP FUNCTION IF EXISTS daemon_cancel_task(UUID);
DROP FUNCTION IF EXISTS daemon_mark_timeouts(INTEGER);
DROP FUNCTION IF EXISTS daemon_retry_task(UUID);

-- Note: RLS policies remain in place for regular user access via anon/authenticated keys
-- The secret key bypasses RLS entirely, so no changes needed to policies
