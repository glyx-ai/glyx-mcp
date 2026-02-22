-- Add working directory columns to paired_devices for GLY-117
-- Allows iOS app to set/persist working directory per device for agent tasks

-- Current working directory for agent tasks
ALTER TABLE paired_devices
ADD COLUMN IF NOT EXISTS working_directory TEXT DEFAULT '~';

-- Recently used directories for quick switching (stored as JSON array)
ALTER TABLE paired_devices
ADD COLUMN IF NOT EXISTS recent_directories JSONB DEFAULT '[]'::jsonb;

-- Add comments for documentation
COMMENT ON COLUMN paired_devices.working_directory IS 'Current working directory for agent tasks on this device. Defaults to home (~).';
COMMENT ON COLUMN paired_devices.recent_directories IS 'Recently used directories as JSON array for quick switching. Max 5 entries.';
