CREATE TABLE studio_directory_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    sequence bigint NOT NULL CHECK (sequence > 0),
    revision text NOT NULL CHECK (revision ~ '^[0-9a-f]{64}$'),
    confirmed_at timestamptz NOT NULL
);
