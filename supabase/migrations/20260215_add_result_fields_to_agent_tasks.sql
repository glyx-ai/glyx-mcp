-- Add result fields to agent_tasks for streaming output and execution results
-- Task 1.1 of Orchestrator MVP PRD

-- output: Stores streaming output from agent execution (appended to during execution)
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS output TEXT;

-- error: Stores error messages if task fails
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS error TEXT;

-- exit_code: Exit code from agent process (0 = success)
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS exit_code INTEGER;

-- started_at: Timestamp when daemon started executing the task
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;

-- completed_at: Timestamp when task finished (success or failure)
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Add comments for documentation
COMMENT ON COLUMN agent_tasks.output IS 'Streaming output from agent execution, appended during execution';
COMMENT ON COLUMN agent_tasks.error IS 'Error message if task failed';
COMMENT ON COLUMN agent_tasks.exit_code IS 'Process exit code (0 = success)';
COMMENT ON COLUMN agent_tasks.started_at IS 'Timestamp when daemon began execution';
COMMENT ON COLUMN agent_tasks.completed_at IS 'Timestamp when task finished';
