-- Enable Supabase Realtime for agent_tasks table
-- Task 1.3 of Orchestrator MVP PRD
--
-- This allows iOS clients to subscribe to real-time updates when:
-- - Task status changes (pending → running → completed/failed)
-- - Output is appended during streaming
-- - Errors occur

-- Add agent_tasks to the supabase_realtime publication
-- This enables Postgres Changes subscriptions from clients
ALTER PUBLICATION supabase_realtime ADD TABLE agent_tasks;

-- Enable REPLICA IDENTITY FULL so UPDATE events include both old and new values
-- This is required for clients to see what changed in each update
ALTER TABLE agent_tasks REPLICA IDENTITY FULL;

-- Add a comment documenting the realtime setup
COMMENT ON TABLE agent_tasks IS 'Tasks dispatched to agents on paired devices. Realtime-enabled for live status updates.';
