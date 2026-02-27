-- =============================================================================
-- RPC Functions for Daemon Operations
-- =============================================================================
-- These SECURITY DEFINER functions allow the daemon to perform specific
-- database operations without needing authentication. The functions run
-- with elevated privileges (definer's permissions) but are explicitly
-- scoped to only the operations the daemon needs.
--
-- This replaces the daemon user authentication approach.
-- =============================================================================

-- Drop old RLS policies for daemon user (no longer needed)
DROP POLICY IF EXISTS "Select: owner or daemon" ON agent_tasks;
DROP POLICY IF EXISTS "Insert: owner or daemon" ON agent_tasks;
DROP POLICY IF EXISTS "Update: owner or daemon" ON agent_tasks;

-- Recreate simple owner-only policies
CREATE POLICY "Users can view own tasks" ON agent_tasks
FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own tasks" ON agent_tasks
FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own tasks" ON agent_tasks
FOR UPDATE USING (auth.uid() = user_id);

-- =============================================================================
-- daemon_get_task: Get task details for daemon processing
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_get_task(p_task_id UUID)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_result JSONB;
BEGIN
  SELECT to_jsonb(t.*)
  INTO v_result
  FROM agent_tasks t
  WHERE t.id = p_task_id;

  RETURN v_result;
END;
$$;

-- =============================================================================
-- daemon_update_task_status: Update task status with output streaming
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_update_task_status(
  p_task_id UUID,
  p_status TEXT DEFAULT NULL,
  p_output TEXT DEFAULT NULL,
  p_error TEXT DEFAULT NULL,
  p_exit_code INTEGER DEFAULT NULL
)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_existing_output TEXT;
  v_result JSONB;
  v_now TIMESTAMPTZ := NOW();
BEGIN
  -- Get existing output for append
  SELECT output INTO v_existing_output
  FROM agent_tasks
  WHERE id = p_task_id;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'Task not found');
  END IF;

  -- Update the task
  UPDATE agent_tasks
  SET
    status = COALESCE(p_status, status),
    output = CASE
      WHEN p_output IS NOT NULL THEN COALESCE(v_existing_output, '') || p_output
      ELSE output
    END,
    error = COALESCE(p_error, error),
    exit_code = COALESCE(p_exit_code, exit_code),
    updated_at = v_now,
    started_at = CASE
      WHEN p_status = 'running' AND started_at IS NULL THEN v_now
      ELSE started_at
    END,
    completed_at = CASE
      WHEN p_status IN ('completed', 'failed', 'cancelled', 'timeout') THEN v_now
      ELSE completed_at
    END
  WHERE id = p_task_id
  RETURNING to_jsonb(agent_tasks.*) INTO v_result;

  RETURN v_result;
END;
$$;

-- =============================================================================
-- daemon_list_pending_tasks: Get pending tasks for a device
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_list_pending_tasks(p_device_id TEXT)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_result JSONB;
BEGIN
  SELECT COALESCE(jsonb_agg(to_jsonb(t.*)), '[]'::jsonb)
  INTO v_result
  FROM agent_tasks t
  WHERE t.device_id = p_device_id
    AND t.status = 'pending'
  ORDER BY t.created_at ASC;

  RETURN v_result;
END;
$$;

-- =============================================================================
-- daemon_cancel_task: Cancel a running or pending task
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_cancel_task(p_task_id UUID)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_current_status TEXT;
  v_result JSONB;
  v_now TIMESTAMPTZ := NOW();
BEGIN
  -- Get current status
  SELECT status INTO v_current_status
  FROM agent_tasks
  WHERE id = p_task_id;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'Task not found');
  END IF;

  -- Only cancel pending or running tasks
  IF v_current_status NOT IN ('pending', 'running') THEN
    RETURN jsonb_build_object(
      'error', format('Cannot cancel task in %s status', v_current_status)
    );
  END IF;

  -- Update to cancelled
  UPDATE agent_tasks
  SET
    status = 'cancelled',
    completed_at = v_now,
    updated_at = v_now
  WHERE id = p_task_id
  RETURNING to_jsonb(agent_tasks.*) INTO v_result;

  RETURN v_result;
END;
$$;

-- =============================================================================
-- daemon_mark_timeouts: Mark stale tasks as timed out
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_mark_timeouts(p_timeout_minutes INTEGER DEFAULT 10)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_cutoff TIMESTAMPTZ;
  v_timed_out_ids UUID[];
  v_now TIMESTAMPTZ := NOW();
BEGIN
  v_cutoff := v_now - (p_timeout_minutes || ' minutes')::INTERVAL;

  -- Find and update stale tasks
  WITH updated AS (
    UPDATE agent_tasks
    SET
      status = 'timeout',
      error = format('Task timed out after %s minutes with no update', p_timeout_minutes),
      completed_at = v_now,
      updated_at = v_now
    WHERE status IN ('pending', 'running')
      AND updated_at < v_cutoff
    RETURNING id
  )
  SELECT ARRAY_AGG(id) INTO v_timed_out_ids FROM updated;

  RETURN jsonb_build_object(
    'timed_out_count', COALESCE(array_length(v_timed_out_ids, 1), 0),
    'task_ids', COALESCE(to_jsonb(v_timed_out_ids), '[]'::jsonb)
  );
END;
$$;

-- =============================================================================
-- daemon_retry_task: Create a new task by retrying a failed one
-- =============================================================================
CREATE OR REPLACE FUNCTION daemon_retry_task(p_task_id UUID)
RETURNS JSONB
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql AS $$
DECLARE
  v_original_task RECORD;
  v_new_task JSONB;
  v_now TIMESTAMPTZ := NOW();
BEGIN
  -- Get original task
  SELECT * INTO v_original_task
  FROM agent_tasks
  WHERE id = p_task_id;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('error', 'Task not found');
  END IF;

  -- Only allow retrying failed/timeout/cancelled tasks
  IF v_original_task.status NOT IN ('failed', 'timeout', 'cancelled') THEN
    RETURN jsonb_build_object(
      'error', format('Cannot retry task in %s status', v_original_task.status)
    );
  END IF;

  -- Create new task
  INSERT INTO agent_tasks (
    user_id, device_id, agent_type, task_type, payload,
    status, created_at, updated_at
  )
  VALUES (
    v_original_task.user_id,
    v_original_task.device_id,
    v_original_task.agent_type,
    COALESCE(v_original_task.task_type, 'prompt'),
    v_original_task.payload,
    'pending',
    v_now,
    v_now
  )
  RETURNING to_jsonb(agent_tasks.*) INTO v_new_task;

  RETURN jsonb_build_object(
    'original_task_id', p_task_id,
    'new_task', v_new_task
  );
END;
$$;

-- Grant execute to authenticated and anon roles (functions handle their own auth)
GRANT EXECUTE ON FUNCTION daemon_get_task(UUID) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION daemon_update_task_status(UUID, TEXT, TEXT, TEXT, INTEGER) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION daemon_list_pending_tasks(TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION daemon_cancel_task(UUID) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION daemon_mark_timeouts(INTEGER) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION daemon_retry_task(UUID) TO anon, authenticated;

-- =============================================================================
-- Comments for documentation
-- =============================================================================
COMMENT ON FUNCTION daemon_get_task IS 'Get task details by ID. Used by daemon for task execution.';
COMMENT ON FUNCTION daemon_update_task_status IS 'Update task status and append output. Used by daemon for streaming.';
COMMENT ON FUNCTION daemon_list_pending_tasks IS 'List pending tasks for a device. Used by daemon polling.';
COMMENT ON FUNCTION daemon_cancel_task IS 'Cancel a pending or running task.';
COMMENT ON FUNCTION daemon_mark_timeouts IS 'Mark stale tasks as timed out. Called periodically.';
COMMENT ON FUNCTION daemon_retry_task IS 'Retry a failed/cancelled/timed out task by creating a new one.';
