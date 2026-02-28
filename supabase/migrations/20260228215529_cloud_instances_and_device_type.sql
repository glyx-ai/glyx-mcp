-- Cloud MCP instances: one per user, provisioned via API
-- Also extends paired_devices with device_type and mcp_endpoint for cloud devices

-- 1. Create cloud_instances table
CREATE TABLE cloud_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
    service_name TEXT NOT NULL,
    endpoint TEXT,
    status TEXT DEFAULT 'provisioning',  -- provisioning | ready | error | deleted
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE cloud_instances ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own instances" ON cloud_instances
    FOR ALL USING (auth.uid() = user_id);

COMMENT ON TABLE cloud_instances IS 'Per-user Cloud Run MCP server instances';

-- 2. Add device_type and mcp_endpoint to paired_devices
ALTER TABLE paired_devices
ADD COLUMN IF NOT EXISTS device_type TEXT DEFAULT 'local';

ALTER TABLE paired_devices
ADD COLUMN IF NOT EXISTS mcp_endpoint TEXT;

COMMENT ON COLUMN paired_devices.device_type IS 'Type of device: local (QR-paired Mac) or cloud (Cloud Run instance)';
COMMENT ON COLUMN paired_devices.mcp_endpoint IS 'MCP server endpoint URL for cloud devices';
