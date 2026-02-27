-- Add last_seen column to paired_devices for daemon heartbeat tracking
-- This allows the iOS app to know if a device's daemon is online

ALTER TABLE paired_devices
ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT NULL;

-- Add index for efficient queries on last_seen
CREATE INDEX IF NOT EXISTS idx_paired_devices_last_seen
ON paired_devices(last_seen DESC NULLS LAST);

-- Add comment for documentation
COMMENT ON COLUMN paired_devices.last_seen IS 'Last time the daemon sent a heartbeat. NULL means never seen.';
