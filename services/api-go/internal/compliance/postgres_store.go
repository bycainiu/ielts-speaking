package compliance

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

func (s PostgresStore) SaveConsent(ctx context.Context, userID string, input SaveConsentInput) (ConsentRecord, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return ConsentRecord{}, err
	}
	metadata, err := marshalObject(input.Metadata)
	if err != nil {
		return ConsentRecord{}, err
	}
	return scanConsentRecord(s.db.QueryRowContext(ctx, `
		insert into consent_records (user_id, consent_type, version, accepted, accepted_at, metadata)
		values ($1::uuid, $2, $3, $4, case when $4 then now() else null end, $5::jsonb)
		returning id::text, user_id::text, consent_type, version, accepted, accepted_at, metadata, created_at
	`, userID, input.ConsentType, input.Version, input.Accepted, metadata))
}

func (s PostgresStore) ListConsents(ctx context.Context, userID string, consentType string) ([]ConsentRecord, error) {
	consentType = strings.TrimSpace(consentType)
	args := []any{userID}
	conditions := []string{"user_id = $1::uuid"}
	if consentType != "" {
		args = append(args, consentType)
		conditions = append(conditions, fmt.Sprintf("consent_type = $%d", len(args)))
	}
	query := fmt.Sprintf(`
		select id::text, user_id::text, consent_type, version, accepted, accepted_at, metadata, created_at
		from consent_records
		where %s
		order by created_at desc
		limit 50
	`, strings.Join(conditions, " and "))
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []ConsentRecord{}
	for rows.Next() {
		item, err := scanConsentRecord(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) DeleteUserData(ctx context.Context, userID string, input DataDeletionInput) (DataDeletionResult, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return DataDeletionResult{}, err
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return DataDeletionResult{}, err
	}
	defer tx.Rollback()

	if input.SessionID != nil {
		if err := ensureOwnedSession(ctx, tx, userID, *input.SessionID); err != nil {
			return DataDeletionResult{}, err
		}
	}

	result := DataDeletionResult{}
	if input.DeleteRecordings {
		count, err := markAudioDeleted(ctx, tx, userID, input.SessionID)
		if err != nil {
			return DataDeletionResult{}, err
		}
		result.AudioAssetsDeleted = count
	}
	if input.DeleteReports {
		count, err := markSessionsDeleted(ctx, tx, userID, input.SessionID)
		if err != nil {
			return DataDeletionResult{}, err
		}
		result.SessionsDeleted = count
	}
	if input.DeleteBackground {
		count, err := deleteBackground(ctx, tx, userID)
		if err != nil {
			return DataDeletionResult{}, err
		}
		result.BackgroundItemsDeleted = count
	}

	if err := tx.Commit(); err != nil {
		return DataDeletionResult{}, err
	}
	return result, nil
}

func (s PostgresStore) GetVoiceClonePolicy(ctx context.Context) (VoiceClonePolicy, error) {
	var raw []byte
	var updatedBy sql.NullString
	var updatedAt time.Time
	err := s.db.QueryRowContext(ctx, `
		select value, updated_by::text, updated_at
		from app_settings
		where key = $1
	`, VoiceClonePolicyKey).Scan(&raw, &updatedBy, &updatedAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return defaultVoiceClonePolicy(time.Now().UTC()), nil
		}
		return VoiceClonePolicy{}, mapError(err)
	}
	return parseVoiceClonePolicy(raw, updatedBy, updatedAt)
}

func (s PostgresStore) UpdateVoiceClonePolicy(ctx context.Context, actorUserID string, input UpdateVoiceClonePolicyInput) (VoiceClonePolicy, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return VoiceClonePolicy{}, err
	}
	requiresConsent := true
	if input.RequiresExplicitConsent != nil {
		requiresConsent = *input.RequiresExplicitConsent
	}
	value, err := json.Marshal(map[string]any{
		"enabled":                   input.Enabled,
		"version":                   input.Version,
		"requires_explicit_consent": requiresConsent,
	})
	if err != nil {
		return VoiceClonePolicy{}, err
	}

	var raw []byte
	var updatedBy sql.NullString
	var updatedAt time.Time
	err = s.db.QueryRowContext(ctx, `
		insert into app_settings (key, value, updated_by, updated_at)
		values ($1, $2::jsonb, nullif($3, '')::uuid, now())
		on conflict (key) do update set
			value = excluded.value,
			updated_by = excluded.updated_by,
			updated_at = now()
		returning value, updated_by::text, updated_at
	`, VoiceClonePolicyKey, value, actorUserID).Scan(&raw, &updatedBy, &updatedAt)
	if err != nil {
		return VoiceClonePolicy{}, mapError(err)
	}
	return parseVoiceClonePolicy(raw, updatedBy, updatedAt)
}

func ensureOwnedSession(ctx context.Context, tx *sql.Tx, userID string, sessionID string) error {
	var exists bool
	if err := tx.QueryRowContext(ctx, `
		select exists(
			select 1 from practice_sessions
			where id = $1::uuid and user_id = $2::uuid and deleted_at is null
		)
	`, sessionID, userID).Scan(&exists); err != nil {
		return mapError(err)
	}
	if !exists {
		return ErrNotFound
	}
	return nil
}

func markAudioDeleted(ctx context.Context, tx *sql.Tx, userID string, sessionID *string) (int, error) {
	args := []any{userID}
	sessionClause := ""
	if sessionID != nil {
		args = append(args, *sessionID)
		sessionClause = fmt.Sprintf(" and a.session_id = $%d::uuid", len(args))
	}
	query := fmt.Sprintf(`
		update audio_assets a
		set deleted_at = now()
		where a.deleted_at is null
		  and (
			a.user_id = $1::uuid
			or exists (
				select 1 from practice_sessions ps
				where ps.id = a.session_id and ps.user_id = $1::uuid and ps.deleted_at is null
			)
		  )
		  %s
	`, sessionClause)
	result, err := tx.ExecContext(ctx, query, args...)
	if err != nil {
		return 0, mapError(err)
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return 0, err
	}
	return int(rows), nil
}

func markSessionsDeleted(ctx context.Context, tx *sql.Tx, userID string, sessionID *string) (int, error) {
	args := []any{userID}
	conditions := []string{"user_id = $1::uuid", "deleted_at is null"}
	if sessionID != nil {
		args = append(args, *sessionID)
		conditions = append(conditions, fmt.Sprintf("id = $%d::uuid", len(args)))
	}
	query := fmt.Sprintf(`
		update practice_sessions
		set deleted_at = now(), updated_at = now()
		where %s
	`, strings.Join(conditions, " and "))
	result, err := tx.ExecContext(ctx, query, args...)
	if err != nil {
		return 0, mapError(err)
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return 0, err
	}
	return int(rows), nil
}

func deleteBackground(ctx context.Context, tx *sql.Tx, userID string) (int, error) {
	total := 0
	for _, statement := range []string{
		`delete from background_facts where user_id = $1::uuid`,
		`delete from background_questionnaires where user_id = $1::uuid`,
		`update user_profiles set deleted_at = now(), updated_at = now() where user_id = $1::uuid and deleted_at is null`,
	} {
		result, err := tx.ExecContext(ctx, statement, userID)
		if err != nil {
			return 0, mapError(err)
		}
		rows, err := result.RowsAffected()
		if err != nil {
			return 0, err
		}
		total += int(rows)
	}
	return total, nil
}

func scanConsentRecord(row interface{ Scan(dest ...any) error }) (ConsentRecord, error) {
	var item ConsentRecord
	var acceptedAt sql.NullTime
	var metadata []byte
	err := row.Scan(&item.ID, &item.UserID, &item.ConsentType, &item.Version, &item.Accepted, &acceptedAt, &metadata, &item.CreatedAt)
	if err != nil {
		return ConsentRecord{}, mapError(err)
	}
	if acceptedAt.Valid {
		item.AcceptedAt = &acceptedAt.Time
	}
	item.Metadata = json.RawMessage(defaultJSON(metadata, "{}"))
	return item, nil
}

func parseVoiceClonePolicy(raw []byte, updatedBy sql.NullString, updatedAt time.Time) (VoiceClonePolicy, error) {
	payload := struct {
		Enabled                 bool   `json:"enabled"`
		Version                 string `json:"version"`
		RequiresExplicitConsent bool   `json:"requires_explicit_consent"`
	}{
		Version:                 VoiceClonePolicyVersion,
		RequiresExplicitConsent: true,
	}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			return VoiceClonePolicy{}, err
		}
	}
	if payload.Version == "" {
		payload.Version = VoiceClonePolicyVersion
	}
	policy := VoiceClonePolicy{
		Enabled:                 payload.Enabled,
		Version:                 payload.Version,
		RequiresExplicitConsent: payload.RequiresExplicitConsent,
		UpdatedAt:               updatedAt,
	}
	if updatedBy.Valid {
		policy.UpdatedBy = &updatedBy.String
	}
	return policy, nil
}

func defaultVoiceClonePolicy(updatedAt time.Time) VoiceClonePolicy {
	return VoiceClonePolicy{
		Enabled:                 false,
		Version:                 VoiceClonePolicyVersion,
		RequiresExplicitConsent: true,
		UpdatedAt:               updatedAt,
	}
}

func marshalObject(value map[string]any) ([]byte, error) {
	if value == nil {
		value = map[string]any{}
	}
	return json.Marshal(value)
}

func defaultJSON(value []byte, fallback string) []byte {
	if len(value) == 0 {
		return []byte(fallback)
	}
	return value
}

func mapError(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	return err
}
