-- +goose Up
CREATE TABLE tts_cache (
    cache_key text PRIMARY KEY,
    text_hash text NOT NULL,
    voice_id text NOT NULL,
    speaking_rate numeric(4, 2) NOT NULL,
    emotion text NOT NULL,
    style text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    mime_type text NOT NULL,
    audio_base64 text NOT NULL,
    duration_ms integer NOT NULL CHECK (duration_ms > 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX tts_cache_expires_idx ON tts_cache (expires_at);
CREATE INDEX tts_cache_voice_style_idx ON tts_cache (voice_id, style, speaking_rate);

CREATE TRIGGER tts_cache_set_updated_at BEFORE UPDATE ON tts_cache FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS tts_cache_set_updated_at ON tts_cache;
DROP TABLE IF EXISTS tts_cache;
