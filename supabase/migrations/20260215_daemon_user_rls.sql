-- RLS policies for daemon service user to manage agent_tasks
-- The daemon authenticates as a Supabase user and needs to read/update all tasks

-- First, ensure RLS is enabled
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (to avoid conflicts)
DROP POLICY IF EXISTS "Users can view own tasks" ON agent_tasks;
DROP POLICY IF EXISTS "Users can update own tasks" ON agent_tasks;
DROP POLICY IF EXISTS "Daemon can view all tasks" ON agent_tasks;
DROP POLICY IF EXISTS "Daemon can update all tasks" ON agent_tasks;
DROP POLICY IF EXISTS "Users can insert own tasks" ON agent_tasks;

-- Users can view their own tasks
CREATE POLICY "Users can view own tasks" ON agent_tasks
FOR SELECT USING (
    auth.uid() = user_id
);

-- Users can insert tasks for themselves
CREATE POLICY "Users can insert own tasks" ON agent_tasks
FOR INSERT WITH CHECK (
    auth.uid() = user_id
);

-- Users can update their own tasks
CREATE POLICY "Users can update own tasks" ON agent_tasks
FOR UPDATE USING (
    auth.uid() = user_id
);

-- Daemon service user can view ALL tasks (identified by email)
CREATE POLICY "Daemon can view all tasks" ON agent_tasks
FOR SELECT USING (
    auth.jwt() ->> 'email' = 'daemon@glyx.ai'
);

-- Daemon service user can update ALL tasks
CREATE POLICY "Daemon can update all tasks" ON agent_tasks
FOR UPDATE USING (
    auth.jwt() ->> 'email' = 'daemon@glyx.ai'
);

COMMENT ON POLICY "Daemon can view all tasks" ON agent_tasks IS 'Allows daemon service user to read any task for status updates';
COMMENT ON POLICY "Daemon can update all tasks" ON agent_tasks IS 'Allows daemon service user to update task status and output';
