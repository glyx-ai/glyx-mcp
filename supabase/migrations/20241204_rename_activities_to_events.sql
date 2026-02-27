-- Rename activities table to events
ALTER TABLE IF EXISTS activities RENAME TO events;

-- Update any indexes (if they reference the old table name)
-- Note: PostgreSQL automatically renames indexes when table is renamed,
-- but if you have explicit index names, you may want to rename them too:
-- ALTER INDEX IF EXISTS activities_pkey RENAME TO events_pkey;
-- ALTER INDEX IF EXISTS activities_org_id_idx RENAME TO events_org_id_idx;
