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
DROP POLICY IF EXISTS "Select: owner or daemon" ON agent_tasks;
DROP POLICY IF EXISTS "Insert: owner or daemon" ON agent_tasks;
DROP POLICY IF EXISTS "Update: owner or daemon" ON agent_tasks;

-- Combined policies: owner OR daemon can access
-- Uses auth.email() to check for daemon user
CREATE POLICY "Select: owner or daemon" ON agent_tasks
FOR SELECT USING (
    auth.uid() = user_id OR auth.email() = 'daemon@glyx.ai'
);

CREATE POLICY "Insert: owner or daemon" ON agent_tasks
FOR INSERT WITH CHECK (
    auth.uid() = user_id OR auth.email() = 'daemon@glyx.ai'
);

CREATE POLICY "Update: owner or daemon" ON agent_tasks
FOR UPDATE USING (
    auth.uid() = user_id OR auth.email() = 'daemon@glyx.ai'
);
