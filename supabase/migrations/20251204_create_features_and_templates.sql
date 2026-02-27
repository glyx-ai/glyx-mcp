-- Agent sequences table (pipeline execution instances)
CREATE TABLE IF NOT EXISTS agent_sequences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001'::UUID,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'review', 'testing', 'done')),
    stages JSONB NOT NULL DEFAULT '[]'::JSONB,
    artifacts JSONB NOT NULL DEFAULT '[]'::JSONB,
    events JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_sequences_project_id ON agent_sequences(project_id);
CREATE INDEX idx_agent_sequences_status ON agent_sequences(status);
CREATE INDEX idx_agent_sequences_updated_at ON agent_sequences(updated_at DESC);

-- Workflow templates table (custom pipeline templates)
CREATE TABLE IF NOT EXISTS workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,  -- NULL for global templates
    name TEXT NOT NULL,
    description TEXT,
    template_key TEXT NOT NULL,  -- 'fast_dev', 'full_lifecycle', 'custom', etc.
    stages JSONB NOT NULL,  -- Default stage configuration
    config JSONB DEFAULT '{}'::JSONB,  -- Additional template metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, template_key)
);

CREATE INDEX idx_workflow_templates_user_id ON workflow_templates(user_id);
CREATE INDEX idx_workflow_templates_template_key ON workflow_templates(template_key);
