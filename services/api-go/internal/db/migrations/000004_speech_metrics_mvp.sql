-- +goose Up
ALTER TABLE speech_metrics
    ADD COLUMN IF NOT EXISTS duration_ms integer CHECK (duration_ms IS NULL OR duration_ms > 0),
    ADD COLUMN IF NOT EXISTS words_count integer CHECK (words_count IS NULL OR words_count >= 0),
    ADD COLUMN IF NOT EXISTS filler_count integer CHECK (filler_count IS NULL OR filler_count >= 0),
    ADD COLUMN IF NOT EXISTS mean_pause_ms numeric(8, 2) CHECK (mean_pause_ms IS NULL OR mean_pause_ms >= 0),
    ADD COLUMN IF NOT EXISTS total_pause_ms integer CHECK (total_pause_ms IS NULL OR total_pause_ms >= 0);

CREATE INDEX IF NOT EXISTS speech_metrics_turn_created_desc_idx ON speech_metrics (turn_id, created_at DESC);

-- +goose Down
DROP INDEX IF EXISTS speech_metrics_turn_created_desc_idx;

ALTER TABLE speech_metrics
    DROP COLUMN IF EXISTS total_pause_ms,
    DROP COLUMN IF EXISTS mean_pause_ms,
    DROP COLUMN IF EXISTS filler_count,
    DROP COLUMN IF EXISTS words_count,
    DROP COLUMN IF EXISTS duration_ms;
