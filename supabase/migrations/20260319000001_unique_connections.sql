-- Prevent duplicate SSH connections per user (same host + port + username)
CREATE UNIQUE INDEX idx_ssh_connections_unique_per_user
    ON ssh_connections (user_id, host, port, username);

-- Prevent duplicate paired devices per user (same name + hostname)
CREATE UNIQUE INDEX idx_paired_devices_unique_per_user
    ON paired_devices (user_id, name, hostname);
