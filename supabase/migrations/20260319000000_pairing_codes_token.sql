-- Add claude_token column to pairing_codes for cloud agent provisioning
ALTER TABLE pairing_codes ADD COLUMN claude_token TEXT;
