CREATE TABLE pairing_codes (
    code TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '10 minutes')
);

ALTER TABLE pairing_codes ENABLE ROW LEVEL SECURITY;

-- CLI inserts without auth (anon key)
CREATE POLICY "Anon can insert pairing codes"
    ON pairing_codes FOR INSERT TO anon WITH CHECK (true);

-- Anon can delete expired codes (cleanup on insert)
CREATE POLICY "Anon can delete expired codes"
    ON pairing_codes FOR DELETE TO anon USING (expires_at < NOW());

-- iOS reads with auth
CREATE POLICY "Authenticated can read pairing codes"
    ON pairing_codes FOR SELECT TO authenticated USING (true);

-- Authenticated can delete (cleanup after use)
CREATE POLICY "Authenticated can delete pairing codes"
    ON pairing_codes FOR DELETE TO authenticated USING (true);

CREATE INDEX idx_pairing_codes_expires ON pairing_codes (expires_at);
