-- Run this in your Supabase SQL editor before setting STORAGE_BACKEND=supabase
-- Supabase dashboard → SQL Editor → New query → paste → Run

CREATE TABLE IF NOT EXISTS users (
    user_id   BIGINT PRIMARY KEY,
    data      JSONB  NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Speeds up the startup query that filters by onboarding_step
CREATE INDEX IF NOT EXISTS idx_users_onboarding
    ON users ((data->>'onboarding_step'));

-- Auto-update updated_at on every write
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at ON users;
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
