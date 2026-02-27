-- Drop the activities_actor_check constraint that was left over from the old activities table
-- The actor field should allow any string value
ALTER TABLE events DROP CONSTRAINT IF EXISTS activities_actor_check;
