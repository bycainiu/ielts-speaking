-- +goose Up
ALTER TABLE audio_assets
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

CREATE INDEX IF NOT EXISTS audio_assets_active_session_idx
    ON audio_assets (session_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS app_settings (
    key text PRIMARY KEY,
    value jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(value) = 'object')
);

INSERT INTO app_settings (key, value)
VALUES (
    'voice_clone_policy',
    '{"enabled":false,"version":"voice_clone_policy.v1","requires_explicit_consent":true}'::jsonb
)
ON CONFLICT (key) DO NOTHING;

-- +goose Down
DELETE FROM app_settings WHERE key = 'voice_clone_policy';
DROP TABLE IF EXISTS app_settings;
DROP INDEX IF EXISTS audio_assets_active_session_idx;
ALTER TABLE audio_assets
    DROP COLUMN IF EXISTS deleted_at;
