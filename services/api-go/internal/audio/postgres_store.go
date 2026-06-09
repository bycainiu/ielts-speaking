package audio

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}

func (s PostgresStore) CreateAsset(ctx context.Context, input CreateAssetInput) (Asset, error) {
	if err := s.EnsureTurnForUser(ctx, input.UserID, input.SessionID, input.TurnID); err != nil {
		return Asset{}, err
	}

	checksum := sql.NullString{String: input.ChecksumSHA256, Valid: input.ChecksumSHA256 != ""}
	asset, err := scanAsset(s.db.QueryRowContext(ctx, `
		insert into audio_assets (user_id, session_id, turn_id, kind, storage_bucket, storage_key, mime_type, size_bytes, duration_ms, checksum_sha256)
		values ($1::uuid, $2::uuid, $3::uuid, $4::audio_kind, $5, $6, $7, $8, $9, $10)
		returning id::text, user_id::text, session_id::text, turn_id::text, kind::text, storage_bucket, storage_key,
			mime_type, size_bytes, duration_ms, checksum_sha256, created_at, deleted_at
	`, input.UserID, input.SessionID, input.TurnID, input.Kind, input.StorageBucket, input.StorageKey, input.MimeType, input.SizeBytes, input.DurationMS, checksum))
	if err != nil {
		return Asset{}, mapError(err)
	}
	return asset, nil
}

func (s PostgresStore) GetAssetForUser(ctx context.Context, userID string, assetID string) (Asset, error) {
	asset, err := scanAsset(s.db.QueryRowContext(ctx, `
		select a.id::text, a.user_id::text, a.session_id::text, a.turn_id::text, a.kind::text, a.storage_bucket, a.storage_key,
			a.mime_type, a.size_bytes, a.duration_ms, a.checksum_sha256, a.created_at, a.deleted_at
		from audio_assets a
		left join practice_sessions ps on ps.id = a.session_id
		where a.id = $1::uuid and a.deleted_at is null and (a.user_id = $2::uuid or ps.user_id = $2::uuid) and (ps.deleted_at is null or ps.id is null)
	`, assetID, userID))
	if err != nil {
		return Asset{}, mapError(err)
	}
	return asset, nil
}

func (s PostgresStore) HasAcceptedConsent(ctx context.Context, userID string, consentType string) (bool, error) {
	var accepted bool
	err := s.db.QueryRowContext(ctx, `
		select coalesce((
			select accepted
			from consent_records
			where user_id = $1::uuid and consent_type = $2
			order by created_at desc
			limit 1
		), false)
	`, userID, consentType).Scan(&accepted)
	if err != nil {
		return false, mapError(err)
	}
	return accepted, nil
}

func (s PostgresStore) VoiceCloneEnabled(ctx context.Context) (bool, error) {
	var enabled bool
	err := s.db.QueryRowContext(ctx, `
		select coalesce((value->>'enabled')::boolean, false)
		from app_settings
		where key = 'voice_clone_policy'
	`).Scan(&enabled)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, mapError(err)
	}
	return enabled, nil
}

func (s PostgresStore) GetTTSCache(ctx context.Context, cacheKey string, now time.Time) (TTSCacheEntry, error) {
	entry, err := scanTTSCacheEntry(s.db.QueryRowContext(ctx, `
		select cache_key, text_hash, voice_id, speaking_rate::float8, emotion, style,
			provider, model, mime_type, audio_base64, duration_ms, metadata, expires_at, created_at, updated_at
		from tts_cache
		where cache_key = $1 and expires_at > $2
	`, cacheKey, now))
	if err != nil {
		return TTSCacheEntry{}, mapError(err)
	}
	return entry, nil
}

func (s PostgresStore) SaveTTSCache(ctx context.Context, input SaveTTSCacheInput) (TTSCacheEntry, error) {
	metadata, err := json.Marshal(defaultMap(input.Metadata))
	if err != nil {
		return TTSCacheEntry{}, err
	}
	entry, err := scanTTSCacheEntry(s.db.QueryRowContext(ctx, `
		insert into tts_cache (
			cache_key, text_hash, voice_id, speaking_rate, emotion, style,
			provider, model, mime_type, audio_base64, duration_ms, metadata, expires_at
		)
		values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13)
		on conflict (cache_key) do update set
			provider = excluded.provider,
			model = excluded.model,
			mime_type = excluded.mime_type,
			audio_base64 = excluded.audio_base64,
			duration_ms = excluded.duration_ms,
			metadata = excluded.metadata,
			expires_at = excluded.expires_at,
			updated_at = now()
		returning cache_key, text_hash, voice_id, speaking_rate::float8, emotion, style,
			provider, model, mime_type, audio_base64, duration_ms, metadata, expires_at, created_at, updated_at
	`, input.CacheKey, input.TextHash, input.VoiceID, input.SpeakingRate, input.Emotion, input.Style, input.Provider, input.Model, input.MimeType, input.AudioBase64, input.DurationMS, metadata, input.ExpiresAt))
	if err != nil {
		return TTSCacheEntry{}, mapError(err)
	}
	return entry, nil
}

func (s PostgresStore) CleanupExpiredTTSCache(ctx context.Context, now time.Time) (int, error) {
	result, err := s.db.ExecContext(ctx, `delete from tts_cache where expires_at <= $1`, now)
	if err != nil {
		return 0, mapError(err)
	}
	deleted, err := result.RowsAffected()
	if err != nil {
		return 0, err
	}
	return int(deleted), nil
}

func (s PostgresStore) EnsureTurnForUser(ctx context.Context, userID string, sessionID string, turnID string) error {
	var exists bool
	if err := s.db.QueryRowContext(ctx, `
		select exists(
			select 1
			from session_turns st
			join practice_sessions ps on ps.id = st.session_id
			where st.id = $1::uuid and st.session_id = $2::uuid and ps.user_id = $3::uuid and ps.deleted_at is null
		)
	`, turnID, sessionID, userID).Scan(&exists); err != nil {
		return mapError(err)
	}
	if !exists {
		return ErrNotFound
	}
	return nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanAsset(row rowScanner) (Asset, error) {
	var asset Asset
	var userID sql.NullString
	var sessionID sql.NullString
	var turnID sql.NullString
	var durationMS sql.NullInt64
	var checksum sql.NullString
	var deletedAt sql.NullTime
	err := row.Scan(&asset.ID, &userID, &sessionID, &turnID, &asset.Kind, &asset.StorageBucket, &asset.StorageKey, &asset.MimeType, &asset.SizeBytes, &durationMS, &checksum, &asset.CreatedAt, &deletedAt)
	if err != nil {
		return Asset{}, mapError(err)
	}
	asset.UserID = nullableString(userID)
	asset.SessionID = nullableString(sessionID)
	asset.TurnID = nullableString(turnID)
	if durationMS.Valid {
		value := int(durationMS.Int64)
		asset.DurationMS = &value
	}
	asset.ChecksumSHA256 = nullableString(checksum)
	if deletedAt.Valid {
		asset.DeletedAt = &deletedAt.Time
	}
	return asset, nil
}

func scanTTSCacheEntry(row rowScanner) (TTSCacheEntry, error) {
	var entry TTSCacheEntry
	var metadata []byte
	err := row.Scan(
		&entry.CacheKey,
		&entry.TextHash,
		&entry.VoiceID,
		&entry.SpeakingRate,
		&entry.Emotion,
		&entry.Style,
		&entry.Provider,
		&entry.Model,
		&entry.MimeType,
		&entry.AudioBase64,
		&entry.DurationMS,
		&metadata,
		&entry.ExpiresAt,
		&entry.CreatedAt,
		&entry.UpdatedAt,
	)
	if err != nil {
		return TTSCacheEntry{}, mapError(err)
	}
	if len(metadata) == 0 {
		entry.Metadata = map[string]any{}
		return entry, nil
	}
	if err := json.Unmarshal(metadata, &entry.Metadata); err != nil {
		return TTSCacheEntry{}, err
	}
	return entry, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	return &value.String
}

func mapError(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	if err == nil {
		return nil
	}
	message := err.Error()
	if strings.Contains(message, "duplicate key value") {
		return ErrDuplicateAsset
	}
	if strings.Contains(message, "invalid input value for enum") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}

func defaultMap(value map[string]any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	return value
}
