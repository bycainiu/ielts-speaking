-- +goose Up
ALTER TABLE asr_results
    ADD COLUMN IF NOT EXISTS corrected_transcript text,
    ADD COLUMN IF NOT EXISTS corrected_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS corrected_at timestamptz,
    ADD COLUMN IF NOT EXISTS raw_response_redacted jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE asr_results
    ADD CONSTRAINT asr_results_raw_response_redacted_object_chk
    CHECK (jsonb_typeof(raw_response_redacted) = 'object');

-- +goose Down
ALTER TABLE asr_results
    DROP CONSTRAINT IF EXISTS asr_results_raw_response_redacted_object_chk;

ALTER TABLE asr_results
    DROP COLUMN IF EXISTS raw_response_redacted,
    DROP COLUMN IF EXISTS corrected_at,
    DROP COLUMN IF EXISTS corrected_by_user_id,
    DROP COLUMN IF EXISTS corrected_transcript;
