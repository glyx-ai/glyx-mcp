-- Create HITL (Human-in-the-Loop) requests table
-- Task 2.1 of Orchestrator MVP PRD
--
-- This table stores requests from agents that need human input before proceeding.
-- Agents create HITL requests via API, users respond via the iOS app.

CREATE TABLE IF NOT EXISTS hitl_requests (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key to the task that created this HITL request
    task_id UUID NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,

    -- Owner of the request (must match task owner)
    user_id UUID NOT NULL,

    -- The question/prompt shown to the user
    prompt TEXT NOT NULL,

    -- Optional predefined choices (e.g., ["Yes", "No", "Cancel"])
    -- If NULL, user can enter freeform text
    options JSONB,

    -- User's response (NULL until responded)
    response TEXT,

    -- Request lifecycle status
    -- pending: waiting for user response
    -- responded: user has submitted a response
    -- expired: request timed out without response
    -- cancelled: task was cancelled before response
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'responded', 'expired', 'cancelled')),

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '5 minutes'
);

-- Index for finding pending requests by user (common query)
CREATE INDEX IF NOT EXISTS idx_hitl_requests_user_pending
    ON hitl_requests(user_id, status)
    WHERE status = 'pending';

-- Index for finding requests by task
CREATE INDEX IF NOT EXISTS idx_hitl_requests_task_id
    ON hitl_requests(task_id);

-- Index for expiration cleanup job
CREATE INDEX IF NOT EXISTS idx_hitl_requests_expires_at
    ON hitl_requests(expires_at)
    WHERE status = 'pending';

-- Add to Realtime publication for live updates
ALTER PUBLICATION supabase_realtime ADD TABLE hitl_requests;

-- Full replica identity for UPDATE/DELETE events in Realtime
ALTER TABLE hitl_requests REPLICA IDENTITY FULL;

-- Documentation
COMMENT ON TABLE hitl_requests IS 'Human-in-the-loop requests from agents needing user input. Realtime-enabled.';
COMMENT ON COLUMN hitl_requests.task_id IS 'The agent_tasks entry that spawned this request';
COMMENT ON COLUMN hitl_requests.prompt IS 'Question or prompt displayed to the user';
COMMENT ON COLUMN hitl_requests.options IS 'Optional JSON array of predefined choices';
COMMENT ON COLUMN hitl_requests.status IS 'Request state: pending, responded, expired, cancelled';
COMMENT ON COLUMN hitl_requests.expires_at IS 'When this request times out (default: 5 minutes from creation)';
