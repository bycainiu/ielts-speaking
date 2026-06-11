package session

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"
)

type PostgresStore struct {
	db                *sql.DB
	traceUserHashSalt string
}

func NewPostgresStore(db *sql.DB, traceUserHashSalt string) PostgresStore {
	return PostgresStore{
		db:                db,
		traceUserHashSalt: strings.TrimSpace(traceUserHashSalt),
	}
}

func (s PostgresStore) CreateSession(ctx context.Context, userID string, input CreateSessionInput) (PracticeSession, error) {
	input = normalizeCreateSessionInput(input)
	parts, err := plannedParts(input)
	if err != nil {
		return PracticeSession{}, err
	}
	state, err := marshalObject(input.State)
	if err != nil {
		return PracticeSession{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	session, err := scanPracticeSession(tx.QueryRowContext(ctx, `
		insert into practice_sessions (user_id, mode, status, season_id, topic_id, target_part, state)
		values ($1::uuid, $2::session_mode, 'created', $3::uuid, $4::uuid, $5, $6::jsonb)
		returning id::text, user_id::text, mode::text, status::text, season_id::text, topic_id::text,
			target_part, state, started_at, completed_at, created_at, updated_at
	`, userID, input.Mode, input.SeasonID, input.TopicID, input.TargetPart, state))
	if err != nil {
		return PracticeSession{}, mapError(err)
	}

	for index, part := range parts {
		if _, err := tx.ExecContext(ctx, `
			insert into session_parts (session_id, part, status, order_index)
			values ($1::uuid, $2, 'created', $3)
		`, session.ID, part, index); err != nil {
			return PracticeSession{}, mapError(err)
		}
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}

	return s.GetSession(ctx, userID, session.ID)
}

func (s PostgresStore) ListSessions(ctx context.Context, userID string, filter SessionFilter) ([]PracticeSession, error) {
	filter = normalizeSessionFilter(filter)
	args := []any{userID}
	conditions := []string{"user_id = $1::uuid", "deleted_at is null"}

	if filter.Mode != "" {
		args = append(args, filter.Mode)
		conditions = append(conditions, fmt.Sprintf("mode = $%d::session_mode", len(args)))
	}
	if filter.Status != "" {
		args = append(args, filter.Status)
		conditions = append(conditions, fmt.Sprintf("status = $%d::session_status", len(args)))
	}

	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select id::text, user_id::text, mode::text, status::text, season_id::text, topic_id::text,
			target_part, state, started_at, completed_at, created_at, updated_at
		from practice_sessions
		where %s
		order by created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	sessions := []PracticeSession{}
	for rows.Next() {
		session, err := scanPracticeSession(rows)
		if err != nil {
			return nil, err
		}
		sessions = append(sessions, session)
	}

	return sessions, rows.Err()
}

func (s PostgresStore) GetSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	session, err := scanPracticeSession(s.db.QueryRowContext(ctx, `
		select id::text, user_id::text, mode::text, status::text, season_id::text, topic_id::text,
			target_part, state, started_at, completed_at, created_at, updated_at
		from practice_sessions
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null
	`, sessionID, userID))
	if err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := s.loadSessionDetails(ctx, &session); err != nil {
		return PracticeSession{}, err
	}
	return session, nil
}

func (s PostgresStore) GetSessionContextsForAdmin(ctx context.Context, sessionIDs []string) ([]AdminSessionContext, error) {
	args, placeholders := buildAdminSessionContextLookup(sessionIDs)
	if len(args) == 0 {
		return []AdminSessionContext{}, nil
	}

	query := fmt.Sprintf(`
		select
			ps.id::text,
			ps.user_id::text,
			u.email,
			up.display_name,
			ps.mode::text,
			ps.status::text,
			ps.season_id::text,
			s.title,
			ps.topic_id::text,
			t.name,
			ps.target_part,
			ps.state,
			ps.started_at,
			ps.completed_at,
			ps.created_at,
			ps.updated_at
		from practice_sessions ps
		join users u on u.id = ps.user_id and u.deleted_at is null
		left join user_profiles up on up.user_id = ps.user_id and up.deleted_at is null
		left join seasons s on s.id = ps.season_id and s.deleted_at is null
		left join topics t on t.id = ps.topic_id and t.deleted_at is null
		where ps.deleted_at is null and ps.id::text in (%s)
		order by ps.updated_at desc
	`, placeholders)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	contexts := make([]AdminSessionContext, 0, len(args))
	for rows.Next() {
		item, scanErr := scanAdminSessionContext(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		contexts = append(contexts, item)
	}
	return contexts, rows.Err()
}

func (s PostgresStore) GetUserContextsByHashForAdmin(ctx context.Context, userHashes []string) ([]AdminUserContext, error) {
	normalizedHashes := normalizeSessionIDs(userHashes)
	if len(normalizedHashes) == 0 {
		return []AdminUserContext{}, nil
	}

	args := make([]any, 0, len(normalizedHashes)+1)
	args = append(args, s.traceUserHashSalt)
	placeholders := make([]string, 0, len(normalizedHashes))
	for index, item := range normalizedHashes {
		args = append(args, item)
		placeholders = append(placeholders, fmt.Sprintf("$%d", index+2))
	}

	query := fmt.Sprintf(`
		select
			u.id::text,
			'sha256:' || encode(digest($1 || ':' || u.id::text, 'sha256'), 'hex'),
			u.email,
			up.display_name,
			u.created_at,
			u.updated_at
		from users u
		left join user_profiles up on up.user_id = u.id and up.deleted_at is null
		where u.deleted_at is null
			and ('sha256:' || encode(digest($1 || ':' || u.id::text, 'sha256'), 'hex')) in (%s)
		order by u.updated_at desc
	`, strings.Join(placeholders, ", "))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	contexts := make([]AdminUserContext, 0, len(normalizedHashes))
	for rows.Next() {
		item, scanErr := scanAdminUserContext(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		contexts = append(contexts, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	return sortAdminUserContextsByLookup(contexts, lookupOrderFromStrings(normalizedHashes)), nil
}

func (s PostgresStore) GetSessionForAdmin(ctx context.Context, sessionID string) (PracticeSession, error) {
	session, err := scanPracticeSession(s.db.QueryRowContext(ctx, `
		select id::text, user_id::text, mode::text, status::text, season_id::text, topic_id::text,
			target_part, state, started_at, completed_at, created_at, updated_at
		from practice_sessions
		where id = $1::uuid and deleted_at is null
	`, sessionID))
	if err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := s.loadSessionDetails(ctx, &session); err != nil {
		return PracticeSession{}, err
	}
	return session, nil
}

func (s PostgresStore) StartSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	result, err := tx.ExecContext(ctx, `
		update practice_sessions
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status in ('created', 'planned', 'paused', 'in_progress')
	`, sessionID, userID)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}

	if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where id = (
			select id from session_parts
			where session_id = $1::uuid
			order by order_index asc
			limit 1
		) and status = 'created'
	`, sessionID); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) PauseSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	result, err := tx.ExecContext(ctx, `
		update practice_sessions
		set status = 'paused'
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status in ('created', 'planned', 'in_progress', 'paused')
	`, sessionID, userID)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}

	if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'paused'
		where session_id = $1::uuid and status = 'in_progress'
	`, sessionID); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) ResumeSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	result, err := tx.ExecContext(ctx, `
		update practice_sessions
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status in ('paused', 'in_progress')
	`, sessionID, userID)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}

	if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where session_id = $1::uuid and status = 'paused'
	`, sessionID); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where id = (
			select id from session_parts
			where session_id = $1::uuid and status = 'created'
			order by order_index asc
			limit 1
		) and not exists (
			select 1 from session_parts
			where session_id = $1::uuid and status = 'in_progress'
		)
	`, sessionID); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) UpdateSessionState(ctx context.Context, userID string, sessionID string, input UpdateSessionStateInput) (PracticeSession, error) {
	state, err := marshalObject(input.State)
	if err != nil {
		return PracticeSession{}, err
	}
	result, err := s.db.ExecContext(ctx, `
		update practice_sessions
		set state = coalesce(state, '{}'::jsonb) || $3::jsonb
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null
	`, sessionID, userID, state)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) CompletePart(ctx context.Context, userID string, sessionID string, part int) (PracticeSession, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	if err := ensureSessionOwnership(ctx, tx, userID, sessionID); err != nil {
		return PracticeSession{}, err
	}

	var completedOrder int
	result, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'completed', completed_at = coalesce(completed_at, now())
		where session_id = $1::uuid and part = $2
	`, sessionID, part)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}
	if err := tx.QueryRowContext(ctx, `select order_index from session_parts where session_id = $1::uuid and part = $2`, sessionID, part).Scan(&completedOrder); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'in_progress', started_at = coalesce(started_at, now())
		where id = (
			select id from session_parts
			where session_id = $1::uuid and order_index > $2 and status = 'created'
			order by order_index asc
			limit 1
		)
	`, sessionID, completedOrder); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) FinishSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return PracticeSession{}, err
	}
	defer tx.Rollback()

	result, err := tx.ExecContext(ctx, `
		update practice_sessions
		set status = 'scoring', completed_at = coalesce(completed_at, now())
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status in ('created', 'planned', 'in_progress', 'scoring')
	`, sessionID, userID)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}

	updated, err := result.RowsAffected()
	if err != nil {
		return PracticeSession{}, mapError(err)
	}

	if updated == 0 {
		var status string
		if err := tx.QueryRowContext(ctx, `
			select status
			from practice_sessions
			where id = $1::uuid and user_id = $2::uuid and deleted_at is null
		`, sessionID, userID).Scan(&status); err != nil {
			return PracticeSession{}, mapError(err)
		}
		if status != StatusCompleted {
			return PracticeSession{}, ErrNotFound
		}
	} else if _, err := tx.ExecContext(ctx, `
		update session_parts
		set status = 'completed', completed_at = coalesce(completed_at, now())
		where session_id = $1::uuid and status <> 'completed'
	`, sessionID); err != nil {
		return PracticeSession{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) CancelSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error) {
	result, err := s.db.ExecContext(ctx, `
		update practice_sessions
		set status = 'cancelled'
		where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status not in ('completed', 'cancelled')
	`, sessionID, userID)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	if err := requireAffected(result); err != nil {
		return PracticeSession{}, err
	}
	return s.GetSession(ctx, userID, sessionID)
}

func (s PostgresStore) CreateTurn(ctx context.Context, userID string, sessionID string, input CreateTurnInput) (SessionTurn, error) {
	input = normalizeCreateTurnInput(input)
	metadata, err := marshalObject(input.Metadata)
	if err != nil {
		return SessionTurn{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return SessionTurn{}, err
	}
	defer tx.Rollback()

	if err := ensureSessionOwnership(ctx, tx, userID, sessionID); err != nil {
		return SessionTurn{}, err
	}

	var partID string
	if err := tx.QueryRowContext(ctx, `
		select id::text from session_parts where session_id = $1::uuid and part = $2
	`, sessionID, input.Part).Scan(&partID); err != nil {
		return SessionTurn{}, mapError(err)
	}

	var turnIndex int
	if err := tx.QueryRowContext(ctx, `
		select coalesce(max(turn_index) + 1, 0) from session_turns where session_id = $1::uuid
	`, sessionID).Scan(&turnIndex); err != nil {
		return SessionTurn{}, mapError(err)
	}

	turn, err := scanTurn(tx.QueryRowContext(ctx, `
		insert into session_turns (session_id, part_id, question_id, turn_index, speaker, status, question_text, answer_text, agent_run_id, metadata)
		values ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6::turn_status, $7, $8, $9, $10::jsonb)
		returning id::text, session_id::text, part_id::text, question_id::text, turn_index, speaker, status::text,
			question_text, answer_text, agent_run_id, metadata, created_at, updated_at
	`, sessionID, partID, input.QuestionID, turnIndex, input.Speaker, input.Status, input.QuestionText, input.AnswerText, input.AgentRunID, metadata))
	if err != nil {
		return SessionTurn{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return SessionTurn{}, err
	}
	return turn, nil
}

func (s PostgresStore) UpdateTurn(ctx context.Context, userID string, sessionID string, turnID string, input UpdateTurnInput) (SessionTurn, error) {
	metadata, err := marshalObject(input.Metadata)
	if err != nil {
		return SessionTurn{}, err
	}

	if err := s.ensureTurnOwnership(ctx, userID, sessionID, turnID); err != nil {
		return SessionTurn{}, err
	}

	turn, err := scanTurn(s.db.QueryRowContext(ctx, `
		update session_turns
		set status = coalesce($4::turn_status, status),
			question_text = coalesce($5, question_text),
			answer_text = coalesce($6, answer_text),
			agent_run_id = coalesce($7, agent_run_id),
			metadata = case when $8::jsonb = '{}'::jsonb then metadata else $8::jsonb end
		where id = $1::uuid and session_id = $2::uuid and session_id in (
			select id from practice_sessions where user_id = $3::uuid and deleted_at is null
		)
		returning id::text, session_id::text, part_id::text, question_id::text, turn_index, speaker, status::text,
			question_text, answer_text, agent_run_id, metadata, created_at, updated_at
	`, turnID, sessionID, userID, input.Status, input.QuestionText, input.AnswerText, input.AgentRunID, metadata))
	if err != nil {
		return SessionTurn{}, mapError(err)
	}
	return turn, nil
}

func (s PostgresStore) AttachAudioAsset(ctx context.Context, userID string, sessionID string, turnID string, input AudioAssetInput) (AudioAsset, error) {
	if err := s.ensureTurnOwnership(ctx, userID, sessionID, turnID); err != nil {
		return AudioAsset{}, err
	}

	audio, err := scanAudioAsset(s.db.QueryRowContext(ctx, `
		insert into audio_assets (user_id, session_id, turn_id, kind, storage_bucket, storage_key, mime_type, size_bytes, duration_ms, checksum_sha256)
		values ($1::uuid, $2::uuid, $3::uuid, $4::audio_kind, $5, $6, $7, $8, $9, $10)
		returning id::text, user_id::text, session_id::text, turn_id::text, kind::text, storage_bucket, storage_key,
			mime_type, size_bytes, duration_ms, checksum_sha256, created_at
	`, userID, sessionID, turnID, input.Kind, input.StorageBucket, input.StorageKey, input.MimeType, input.SizeBytes, input.DurationMS, input.ChecksumSHA256))
	if err != nil {
		return AudioAsset{}, mapError(err)
	}
	return audio, nil
}

func (s PostgresStore) SaveASRResult(ctx context.Context, userID string, sessionID string, turnID string, input ASRResultInput) (ASRResult, error) {
	if err := s.ensureTurnOwnership(ctx, userID, sessionID, turnID); err != nil {
		return ASRResult{}, err
	}
	segments, err := json.Marshal(input.Segments)
	if err != nil {
		return ASRResult{}, err
	}
	if len(segments) == 0 || string(segments) == "null" {
		segments = []byte("[]")
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return ASRResult{}, err
	}
	defer tx.Rollback()

	if err := ensureAudioAssetBelongsToTurn(ctx, tx, turnID, input.AudioAssetID); err != nil {
		return ASRResult{}, err
	}

	rawResponse, err := marshalRedactedObject(input.RawResponse)
	if err != nil {
		return ASRResult{}, err
	}

	asr, err := scanASRResult(tx.QueryRowContext(ctx, `
		insert into asr_results (turn_id, audio_asset_id, provider, model, transcript, confidence, segments, raw_response_redacted)
		values ($1::uuid, $2::uuid, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
		returning id::text, turn_id::text, audio_asset_id::text, provider, model, transcript,
			corrected_transcript, corrected_by_user_id::text, corrected_at,
			confidence::float8, segments, raw_response_redacted, created_at
	`, turnID, input.AudioAssetID, input.Provider, input.Model, input.Transcript, input.Confidence, segments, rawResponse))
	if err != nil {
		return ASRResult{}, mapError(err)
	}

	if _, err := tx.ExecContext(ctx, `
		update session_turns
		set answer_text = case when speaker = 'user' then $2 else answer_text end,
			status = 'completed'
		where id = $1::uuid
	`, turnID, input.Transcript); err != nil {
		return ASRResult{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return ASRResult{}, err
	}
	return asr, nil
}

func (s PostgresStore) CorrectASRResult(ctx context.Context, userID string, sessionID string, turnID string, asrResultID string, input CorrectASRResultInput) (ASRResult, error) {
	if err := s.ensureTurnOwnership(ctx, userID, sessionID, turnID); err != nil {
		return ASRResult{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return ASRResult{}, err
	}
	defer tx.Rollback()

	asr, err := scanASRResult(tx.QueryRowContext(ctx, `
		update asr_results
		set corrected_transcript = $5,
			corrected_by_user_id = $1::uuid,
			corrected_at = now()
		where id = $4::uuid and turn_id = $3::uuid and turn_id in (
			select st.id
			from session_turns st
			join practice_sessions ps on ps.id = st.session_id
			where st.session_id = $2::uuid and ps.user_id = $1::uuid and ps.deleted_at is null
		)
		returning id::text, turn_id::text, audio_asset_id::text, provider, model, transcript,
			corrected_transcript, corrected_by_user_id::text, corrected_at,
			confidence::float8, segments, raw_response_redacted, created_at
	`, userID, sessionID, turnID, asrResultID, input.CorrectedTranscript))
	if err != nil {
		return ASRResult{}, mapError(err)
	}

	if _, err := tx.ExecContext(ctx, `
		update session_turns
		set answer_text = case when speaker = 'user' then $2 else answer_text end
		where id = $1::uuid
	`, turnID, input.CorrectedTranscript); err != nil {
		return ASRResult{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return ASRResult{}, err
	}
	return asr, nil
}

func (s PostgresStore) SaveSpeechMetrics(ctx context.Context, userID string, sessionID string, turnID string, input SpeechMetricsInput) (SpeechMetrics, error) {
	if err := s.ensureTurnOwnership(ctx, userID, sessionID, turnID); err != nil {
		return SpeechMetrics{}, err
	}
	normalized, err := s.normalizeSpeechMetricsInput(ctx, turnID, input)
	if err != nil {
		return SpeechMetrics{}, err
	}
	rawMetrics, err := marshalObject(input.RawMetrics)
	if err != nil {
		return SpeechMetrics{}, err
	}
	rawMetrics, err = mergeSpeechMetricsRawMetrics(rawMetrics, normalized)
	if err != nil {
		return SpeechMetrics{}, err
	}

	metrics, err := scanSpeechMetrics(s.db.QueryRowContext(ctx, `
		insert into speech_metrics (
			turn_id, audio_asset_id, duration_ms, words_count, wpm, long_pause_count,
			mean_pause_ms, total_pause_ms, filler_count, filler_ratio, asr_confidence, raw_metrics
		)
		values ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
		returning id::text, turn_id::text, audio_asset_id::text, wpm::float8, long_pause_count,
			filler_ratio::float8, asr_confidence::float8, raw_metrics, created_at,
			duration_ms, words_count, mean_pause_ms::float8, total_pause_ms, filler_count
	`, turnID, normalized.AudioAssetID, normalized.DurationMS, normalized.WordsCount, normalized.WPM, normalized.LongPauseCount, normalized.MeanPauseMS, normalized.TotalPauseMS, normalized.FillerCount, normalized.FillerRatio, normalized.ASRConfidence, rawMetrics))
	if err != nil {
		return SpeechMetrics{}, mapError(err)
	}
	return metrics, nil
}

func (s PostgresStore) loadSessionDetails(ctx context.Context, session *PracticeSession) error {
	parts, err := s.listParts(ctx, session.ID)
	if err != nil {
		return err
	}
	session.Parts = parts

	turns, err := s.listTurns(ctx, session.ID)
	if err != nil {
		return err
	}
	for index := range turns {
		if err := s.loadTurnDetails(ctx, &turns[index]); err != nil {
			return err
		}
	}
	session.Turns = turns
	return nil
}

func (s PostgresStore) listParts(ctx context.Context, sessionID string) ([]SessionPart, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, session_id::text, part, status::text, order_index, started_at, completed_at, created_at, updated_at
		from session_parts
		where session_id = $1::uuid
		order by order_index asc
	`, sessionID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	parts := []SessionPart{}
	for rows.Next() {
		part, err := scanPart(rows)
		if err != nil {
			return nil, err
		}
		parts = append(parts, part)
	}
	return parts, rows.Err()
}

func (s PostgresStore) listTurns(ctx context.Context, sessionID string) ([]SessionTurn, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, session_id::text, part_id::text, question_id::text, turn_index, speaker, status::text,
			question_text, answer_text, agent_run_id, metadata, created_at, updated_at
		from session_turns
		where session_id = $1::uuid
		order by turn_index asc
	`, sessionID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	turns := []SessionTurn{}
	for rows.Next() {
		turn, err := scanTurn(rows)
		if err != nil {
			return nil, err
		}
		turns = append(turns, turn)
	}
	return turns, rows.Err()
}

func (s PostgresStore) loadTurnDetails(ctx context.Context, turn *SessionTurn) error {
	audioAssets, err := s.listAudioAssets(ctx, turn.ID)
	if err != nil {
		return err
	}
	turn.AudioAssets = audioAssets

	asrResults, err := s.listASRResults(ctx, turn.ID)
	if err != nil {
		return err
	}
	turn.ASRResults = asrResults

	metrics, err := s.listSpeechMetrics(ctx, turn.ID)
	if err != nil {
		return err
	}
	turn.Metrics = metrics
	return nil
}

func (s PostgresStore) listAudioAssets(ctx context.Context, turnID string) ([]AudioAsset, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, user_id::text, session_id::text, turn_id::text, kind::text, storage_bucket, storage_key,
			mime_type, size_bytes, duration_ms, checksum_sha256, created_at
		from audio_assets
		where turn_id = $1::uuid
		order by created_at asc
	`, turnID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []AudioAsset{}
	for rows.Next() {
		item, err := scanAudioAsset(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listASRResults(ctx context.Context, turnID string) ([]ASRResult, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, turn_id::text, audio_asset_id::text, provider, model, transcript,
			corrected_transcript, corrected_by_user_id::text, corrected_at,
			confidence::float8, segments, raw_response_redacted, created_at
		from asr_results
		where turn_id = $1::uuid
		order by created_at asc
	`, turnID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ASRResult{}
	for rows.Next() {
		item, err := scanASRResult(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listSpeechMetrics(ctx context.Context, turnID string) ([]SpeechMetrics, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, turn_id::text, audio_asset_id::text, wpm::float8, long_pause_count,
			filler_ratio::float8, asr_confidence::float8, raw_metrics, created_at,
			duration_ms, words_count, mean_pause_ms::float8, total_pause_ms, filler_count
		from speech_metrics
		where turn_id = $1::uuid
		order by created_at asc
	`, turnID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []SpeechMetrics{}
	for rows.Next() {
		item, err := scanSpeechMetrics(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) ensureTurnOwnership(ctx context.Context, userID string, sessionID string, turnID string) error {
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

type txQuerier interface {
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
}

func ensureSessionOwnership(ctx context.Context, tx txQuerier, userID string, sessionID string) error {
	var exists bool
	if err := tx.QueryRowContext(ctx, `
		select exists(select 1 from practice_sessions where id = $1::uuid and user_id = $2::uuid and deleted_at is null)
	`, sessionID, userID).Scan(&exists); err != nil {
		return mapError(err)
	}
	if !exists {
		return ErrNotFound
	}
	return nil
}

func ensureAudioAssetBelongsToTurn(ctx context.Context, tx txQuerier, turnID string, audioAssetID *string) error {
	if audioAssetID == nil || strings.TrimSpace(*audioAssetID) == "" {
		return nil
	}
	var exists bool
	if err := tx.QueryRowContext(ctx, `
		select exists(select 1 from audio_assets where id = $1::uuid and turn_id = $2::uuid)
	`, *audioAssetID, turnID).Scan(&exists); err != nil {
		return mapError(err)
	}
	if !exists {
		return fmt.Errorf("%w: audio_asset_id must belong to the target turn", ErrInvalidInput)
	}
	return nil
}

func (s PostgresStore) normalizeSpeechMetricsInput(ctx context.Context, turnID string, input SpeechMetricsInput) (SpeechMetricsInput, error) {
	if err := s.ensureSpeechMetricsAudioAsset(ctx, turnID, input.AudioAssetID); err != nil {
		return SpeechMetricsInput{}, err
	}
	durationMS := input.DurationMS
	if durationMS == nil {
		value, err := s.lookupTurnAudioDurationMS(ctx, turnID, input.AudioAssetID)
		if err != nil {
			return SpeechMetricsInput{}, err
		}
		durationMS = value
	}
	transcript := strings.TrimSpace(input.Transcript)
	if transcript == "" {
		latest, err := s.latestTurnTranscript(ctx, turnID)
		if err != nil {
			return SpeechMetricsInput{}, err
		}
		transcript = latest
	}

	wordsCount := input.WordsCount
	if wordsCount == nil {
		value := countSpeechWords(transcript)
		wordsCount = &value
	}
	wpm := input.WPM
	if wpm == nil && durationMS != nil && *durationMS > 0 && wordsCount != nil {
		value := roundFloat(float64(*wordsCount)/(float64(*durationMS)/60000), 2)
		wpm = &value
	}
	fillerCount := input.FillerCount
	if fillerCount == nil {
		value := countSpeechFillers(transcript)
		fillerCount = &value
	}
	fillerRatio := input.FillerRatio
	if fillerRatio == nil && wordsCount != nil && *wordsCount > 0 && fillerCount != nil {
		value := roundFloat(float64(*fillerCount)/float64(*wordsCount), 4)
		fillerRatio = &value
	}
	longPauseCount, meanPauseMS, totalPauseMS := derivePauseMetrics(input)

	input.DurationMS = durationMS
	input.Transcript = transcript
	input.WordsCount = wordsCount
	input.WPM = wpm
	input.FillerCount = fillerCount
	input.FillerRatio = fillerRatio
	input.LongPauseCount = longPauseCount
	input.MeanPauseMS = meanPauseMS
	input.TotalPauseMS = totalPauseMS
	return input, nil
}

func (s PostgresStore) ensureSpeechMetricsAudioAsset(ctx context.Context, turnID string, audioAssetID *string) error {
	if audioAssetID == nil || strings.TrimSpace(*audioAssetID) == "" {
		return nil
	}
	var exists bool
	if err := s.db.QueryRowContext(ctx, `select exists(select 1 from audio_assets where id = $1::uuid and turn_id = $2::uuid)`, *audioAssetID, turnID).Scan(&exists); err != nil {
		return mapError(err)
	}
	if !exists {
		return fmt.Errorf("%w: audio_asset_id must belong to the target turn", ErrInvalidInput)
	}
	return nil
}

func (s PostgresStore) lookupTurnAudioDurationMS(ctx context.Context, turnID string, audioAssetID *string) (*int, error) {
	var duration sql.NullInt64
	var err error
	if audioAssetID != nil && strings.TrimSpace(*audioAssetID) != "" {
		err = s.db.QueryRowContext(ctx, `
			select duration_ms from audio_assets
			where id = $1::uuid and turn_id = $2::uuid
		`, *audioAssetID, turnID).Scan(&duration)
	} else {
		err = s.db.QueryRowContext(ctx, `
			select duration_ms from audio_assets
			where turn_id = $1::uuid and kind = 'user_recording' and duration_ms is not null
			order by created_at desc
			limit 1
		`, turnID).Scan(&duration)
	}
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, mapError(err)
	}
	if !duration.Valid {
		return nil, nil
	}
	value := int(duration.Int64)
	return &value, nil
}

func (s PostgresStore) latestTurnTranscript(ctx context.Context, turnID string) (string, error) {
	var transcript sql.NullString
	err := s.db.QueryRowContext(ctx, `
		select coalesce(corrected_transcript, transcript)
		from asr_results
		where turn_id = $1::uuid
		order by created_at desc
		limit 1
	`, turnID).Scan(&transcript)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", mapError(err)
	}
	if !transcript.Valid {
		return "", nil
	}
	return transcript.String, nil
}

func derivePauseMetrics(input SpeechMetricsInput) (*int, *float64, *int) {
	longPauseCount := input.LongPauseCount
	meanPauseMS := input.MeanPauseMS
	totalPauseMS := input.TotalPauseMS
	if len(input.PauseSegments) == 0 {
		return longPauseCount, meanPauseMS, totalPauseMS
	}
	threshold := 1000
	if input.LongPauseThresholdMS != nil && *input.LongPauseThresholdMS > 0 {
		threshold = *input.LongPauseThresholdMS
	}
	count := 0
	total := 0
	for _, segment := range input.PauseSegments {
		if segment.EndMS < segment.StartMS {
			continue
		}
		duration := segment.EndMS - segment.StartMS
		if duration >= threshold {
			count++
			total += duration
		}
	}
	mean := 0.0
	if count > 0 {
		mean = roundFloat(float64(total)/float64(count), 2)
	}
	if longPauseCount == nil {
		longPauseCount = &count
	}
	if totalPauseMS == nil {
		totalPauseMS = &total
	}
	if meanPauseMS == nil && count > 0 {
		meanPauseMS = &mean
	}
	return longPauseCount, meanPauseMS, totalPauseMS
}

func mergeSpeechMetricsRawMetrics(raw []byte, input SpeechMetricsInput) ([]byte, error) {
	payload := map[string]any{}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &payload); err != nil {
			return nil, err
		}
	}
	payload["computed_mvp"] = true
	payload["transcript_source"] = "request_or_latest_asr"
	if input.LongPauseThresholdMS != nil {
		payload["long_pause_threshold_ms"] = *input.LongPauseThresholdMS
	}
	if len(input.PauseSegments) > 0 {
		payload["pause_segments_count"] = len(input.PauseSegments)
	}
	return json.Marshal(payload)
}

var speechWordPattern = regexp.MustCompile(`[A-Za-z]+(?:'[A-Za-z]+)?`)

func countSpeechWords(text string) int {
	return len(speechWordPattern.FindAllString(text, -1))
}

func countSpeechFillers(text string) int {
	normalized := " " + strings.ToLower(text) + " "
	fillers := []string{"um", "uh", "er", "erm", "ah", "like", "you know", "i mean", "sort of", "kind of"}
	count := 0
	for _, filler := range fillers {
		if strings.Contains(filler, " ") {
			count += len(regexp.MustCompile(`\b`+strings.Join(strings.Fields(regexp.QuoteMeta(filler)), `\s+`)+`\b`).FindAllString(normalized, -1))
			continue
		}
		count += len(regexp.MustCompile(`\b`+regexp.QuoteMeta(filler)+`\b`).FindAllString(normalized, -1))
	}
	return count
}

func roundFloat(value float64, places int) float64 {
	factor := 1.0
	for i := 0; i < places; i++ {
		factor *= 10
	}
	if value >= 0 {
		return float64(int(value*factor+0.5)) / factor
	}
	return float64(int(value*factor-0.5)) / factor
}

func plannedParts(input CreateSessionInput) ([]int, error) {
	switch input.Mode {
	case ModeFullExam:
		return []int{1, 2, 3}, nil
	case ModePartPractice:
		if input.TargetPart == nil {
			return nil, fmt.Errorf("%w: target_part is required for part_practice", ErrInvalidInput)
		}
		return []int{*input.TargetPart}, nil
	case ModeTopicPractice:
		if input.TopicID == nil || strings.TrimSpace(*input.TopicID) == "" {
			return nil, fmt.Errorf("%w: topic_id is required for topic_practice", ErrInvalidInput)
		}
		if input.TargetPart != nil {
			return []int{*input.TargetPart}, nil
		}
		return []int{1, 2, 3}, nil
	default:
		return nil, ErrInvalidInput
	}
}

func normalizeCreateSessionInput(input CreateSessionInput) CreateSessionInput {
	if input.State == nil {
		input.State = map[string]any{}
	}
	return input
}

func normalizeCreateTurnInput(input CreateTurnInput) CreateTurnInput {
	if input.Status == "" {
		input.Status = TurnStatusPending
	}
	if input.Metadata == nil {
		input.Metadata = map[string]any{}
	}
	return input
}

func normalizeSessionFilter(filter SessionFilter) SessionFilter {
	if filter.Limit <= 0 || filter.Limit > 100 {
		filter.Limit = 50
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeSessionIDs(sessionIDs []string) []string {
	if len(sessionIDs) == 0 {
		return []string{}
	}
	items := make([]string, 0, len(sessionIDs))
	seen := make(map[string]struct{}, len(sessionIDs))
	for _, item := range sessionIDs {
		normalized := strings.TrimSpace(item)
		if normalized == "" {
			continue
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		items = append(items, normalized)
		if len(items) >= 200 {
			break
		}
	}
	return items
}

func buildAdminSessionContextLookup(sessionIDs []string) ([]any, string) {
	normalizedIDs := normalizeSessionIDs(sessionIDs)
	if len(normalizedIDs) == 0 {
		return []any{}, ""
	}

	args := make([]any, 0, len(normalizedIDs))
	placeholders := make([]string, 0, len(normalizedIDs))
	for index, sessionID := range normalizedIDs {
		args = append(args, sessionID)
		placeholders = append(placeholders, fmt.Sprintf("$%d", index+1))
	}
	return args, strings.Join(placeholders, ", ")
}

func lookupOrderFromStrings(items []string) map[string]int {
	order := make(map[string]int, len(items))
	for index, item := range items {
		if _, exists := order[item]; exists {
			continue
		}
		order[item] = index
	}
	return order
}

func sortAdminUserContextsByLookup(items []AdminUserContext, order map[string]int) []AdminUserContext {
	if len(items) <= 1 {
		return items
	}
	sort.SliceStable(items, func(left, right int) bool {
		leftOrder, leftOK := order[items[left].UserHash]
		rightOrder, rightOK := order[items[right].UserHash]
		if leftOK && rightOK {
			return leftOrder < rightOrder
		}
		if leftOK != rightOK {
			return leftOK
		}
		return items[left].UpdatedAt.After(items[right].UpdatedAt)
	})
	return items
}

func marshalObject(value map[string]any) ([]byte, error) {
	if value == nil {
		value = map[string]any{}
	}
	return json.Marshal(value)
}

func marshalRedactedObject(value map[string]any) ([]byte, error) {
	if value == nil {
		value = map[string]any{}
	}
	return json.Marshal(redactSensitiveValue(value))
}

func redactSensitiveValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		redacted := make(map[string]any, len(typed))
		for key, nested := range typed {
			if isSensitiveASRRawResponseKey(key) {
				redacted[key] = "[redacted]"
				continue
			}
			redacted[key] = redactSensitiveValue(nested)
		}
		return redacted
	case []any:
		items := make([]any, len(typed))
		for index, nested := range typed {
			items[index] = redactSensitiveValue(nested)
		}
		return items
	default:
		return value
	}
}

func isSensitiveASRRawResponseKey(key string) bool {
	normalized := strings.ToLower(strings.TrimSpace(key))
	sensitiveTokens := []string{
		"api_key",
		"apikey",
		"authorization",
		"bearer",
		"token",
		"secret",
		"password",
		"audio_base64",
		"base64",
		"input_audio",
		"audio_data",
		"data",
	}
	for _, token := range sensitiveTokens {
		if strings.Contains(normalized, token) {
			return true
		}
	}
	return false
}

func requireAffected(result sql.Result) error {
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return ErrNotFound
	}
	return nil
}

func mapError(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	if err == nil {
		return nil
	}
	message := err.Error()
	if strings.Contains(message, "duplicate key value") && strings.Contains(message, "session_turns") {
		return ErrDuplicateTurnIndex
	}
	if strings.Contains(message, "duplicate key value") && strings.Contains(message, "audio_assets") {
		return ErrDuplicateAudioAsset
	}
	if strings.Contains(message, "invalid input value for enum") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanPracticeSession(row rowScanner) (PracticeSession, error) {
	var item PracticeSession
	var seasonID sql.NullString
	var topicID sql.NullString
	var targetPart sql.NullInt64
	var state []byte
	var startedAt sql.NullTime
	var completedAt sql.NullTime
	err := row.Scan(&item.ID, &item.UserID, &item.Mode, &item.Status, &seasonID, &topicID, &targetPart, &state, &startedAt, &completedAt, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return PracticeSession{}, mapError(err)
	}
	item.SeasonID = nullableString(seasonID)
	item.TopicID = nullableString(topicID)
	if targetPart.Valid {
		part := int(targetPart.Int64)
		item.TargetPart = &part
	}
	item.State = json.RawMessage(defaultJSON(state, "{}"))
	item.StartedAt = nullableTime(startedAt)
	item.CompletedAt = nullableTime(completedAt)
	item.Parts = []SessionPart{}
	item.Turns = []SessionTurn{}
	return item, nil
}

func scanAdminSessionContext(row rowScanner) (AdminSessionContext, error) {
	var item AdminSessionContext
	var userDisplayName sql.NullString
	var seasonID sql.NullString
	var seasonTitle sql.NullString
	var topicID sql.NullString
	var topicName sql.NullString
	var targetPart sql.NullInt64
	var state []byte
	var startedAt sql.NullTime
	var completedAt sql.NullTime
	err := row.Scan(
		&item.SessionID,
		&item.UserID,
		&item.UserEmail,
		&userDisplayName,
		&item.Mode,
		&item.Status,
		&seasonID,
		&seasonTitle,
		&topicID,
		&topicName,
		&targetPart,
		&state,
		&startedAt,
		&completedAt,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	if err != nil {
		return AdminSessionContext{}, mapError(err)
	}
	item.UserDisplayName = nullableString(userDisplayName)
	item.SeasonID = nullableString(seasonID)
	item.SeasonTitle = nullableString(seasonTitle)
	item.TopicID = nullableString(topicID)
	item.TopicName = nullableString(topicName)
	if targetPart.Valid {
		part := int(targetPart.Int64)
		item.TargetPart = &part
	}
	item.StartedAt = nullableTime(startedAt)
	item.CompletedAt = nullableTime(completedAt)
	applyAdminSessionStateHints(&item, state)
	return item, nil
}

func scanAdminUserContext(row rowScanner) (AdminUserContext, error) {
	var item AdminUserContext
	var userDisplayName sql.NullString
	err := row.Scan(
		&item.UserID,
		&item.UserHash,
		&item.UserEmail,
		&userDisplayName,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	if err != nil {
		return AdminUserContext{}, mapError(err)
	}
	item.UserDisplayName = nullableString(userDisplayName)
	return item, nil
}

func applyAdminSessionStateHints(item *AdminSessionContext, state []byte) {
	if item == nil || len(state) == 0 {
		return
	}
	var payload map[string]any
	if err := json.Unmarshal(state, &payload); err != nil {
		return
	}
	item.SetupSurface = optionalString(payload["setup_surface"])
	if item.TopicLabel == nil {
		item.TopicLabel = topicLabelFromState(payload)
	}
	if item.PrimaryTopic == nil {
		item.PrimaryTopic = primaryTopicFromState(payload)
	}
}

func topicLabelFromState(payload map[string]any) *string {
	if guidance, ok := payload["topic_guidance"].(map[string]any); ok {
		if label := optionalString(guidance["topic_label"]); label != nil {
			return label
		}
		if labels := stringSliceFromUnknown(guidance["topic_labels"]); len(labels) > 0 {
			return &labels[0]
		}
		if primary := optionalString(guidance["primary_topic"]); primary != nil {
			return primary
		}
	}
	if labels := stringSliceFromUnknown(payload["topic_labels"]); len(labels) > 0 {
		return &labels[0]
	}
	return nil
}

func primaryTopicFromState(payload map[string]any) *string {
	if guidance, ok := payload["topic_guidance"].(map[string]any); ok {
		if primary := optionalString(guidance["primary_topic"]); primary != nil {
			return primary
		}
	}
	return nil
}

func optionalString(value any) *string {
	text, ok := value.(string)
	if !ok {
		return nil
	}
	normalized := strings.TrimSpace(text)
	if normalized == "" {
		return nil
	}
	return &normalized
}

func stringSliceFromUnknown(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return []string{}
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		text, ok := item.(string)
		if !ok {
			continue
		}
		normalized := strings.TrimSpace(text)
		if normalized == "" {
			continue
		}
		result = append(result, normalized)
	}
	return result
}

func scanPart(row rowScanner) (SessionPart, error) {
	var item SessionPart
	var startedAt sql.NullTime
	var completedAt sql.NullTime
	err := row.Scan(&item.ID, &item.SessionID, &item.Part, &item.Status, &item.OrderIndex, &startedAt, &completedAt, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return SessionPart{}, mapError(err)
	}
	item.StartedAt = nullableTime(startedAt)
	item.CompletedAt = nullableTime(completedAt)
	return item, nil
}

func scanTurn(row rowScanner) (SessionTurn, error) {
	var item SessionTurn
	var partID sql.NullString
	var questionID sql.NullString
	var questionText sql.NullString
	var answerText sql.NullString
	var agentRunID sql.NullString
	var metadata []byte
	err := row.Scan(&item.ID, &item.SessionID, &partID, &questionID, &item.TurnIndex, &item.Speaker, &item.Status, &questionText, &answerText, &agentRunID, &metadata, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return SessionTurn{}, mapError(err)
	}
	item.PartID = nullableString(partID)
	item.QuestionID = nullableString(questionID)
	item.QuestionText = nullableString(questionText)
	item.AnswerText = nullableString(answerText)
	item.AgentRunID = nullableString(agentRunID)
	item.Metadata = json.RawMessage(defaultJSON(metadata, "{}"))
	item.AudioAssets = []AudioAsset{}
	item.ASRResults = []ASRResult{}
	item.Metrics = []SpeechMetrics{}
	return item, nil
}

func scanAudioAsset(row rowScanner) (AudioAsset, error) {
	var item AudioAsset
	var userID sql.NullString
	var sessionID sql.NullString
	var turnID sql.NullString
	var durationMS sql.NullInt64
	var checksum sql.NullString
	err := row.Scan(&item.ID, &userID, &sessionID, &turnID, &item.Kind, &item.StorageBucket, &item.StorageKey, &item.MimeType, &item.SizeBytes, &durationMS, &checksum, &item.CreatedAt)
	if err != nil {
		return AudioAsset{}, mapError(err)
	}
	item.UserID = nullableString(userID)
	item.SessionID = nullableString(sessionID)
	item.TurnID = nullableString(turnID)
	if durationMS.Valid {
		value := int(durationMS.Int64)
		item.DurationMS = &value
	}
	item.ChecksumSHA256 = nullableString(checksum)
	return item, nil
}

func scanASRResult(row rowScanner) (ASRResult, error) {
	var item ASRResult
	var audioAssetID sql.NullString
	var correctedTranscript sql.NullString
	var correctedByUserID sql.NullString
	var correctedAt sql.NullTime
	var confidence sql.NullFloat64
	var segments []byte
	var rawResponseRedacted []byte
	err := row.Scan(
		&item.ID,
		&item.TurnID,
		&audioAssetID,
		&item.Provider,
		&item.Model,
		&item.Transcript,
		&correctedTranscript,
		&correctedByUserID,
		&correctedAt,
		&confidence,
		&segments,
		&rawResponseRedacted,
		&item.CreatedAt,
	)
	if err != nil {
		return ASRResult{}, mapError(err)
	}
	item.AudioAssetID = nullableString(audioAssetID)
	item.CorrectedTranscript = nullableString(correctedTranscript)
	item.CorrectedByUserID = nullableString(correctedByUserID)
	item.CorrectedAt = nullableTime(correctedAt)
	item.Confidence = nullableFloat(confidence)
	item.Segments = json.RawMessage(defaultJSON(segments, "[]"))
	item.RawResponseRedacted = json.RawMessage(defaultJSON(rawResponseRedacted, "{}"))
	return item, nil
}

func scanSpeechMetrics(row rowScanner) (SpeechMetrics, error) {
	var item SpeechMetrics
	var audioAssetID sql.NullString
	var durationMS sql.NullInt64
	var wordsCount sql.NullInt64
	var wpm sql.NullFloat64
	var longPauseCount sql.NullInt64
	var meanPauseMS sql.NullFloat64
	var totalPauseMS sql.NullInt64
	var fillerCount sql.NullInt64
	var fillerRatio sql.NullFloat64
	var asrConfidence sql.NullFloat64
	var rawMetrics []byte
	err := row.Scan(&item.ID, &item.TurnID, &audioAssetID, &wpm, &longPauseCount, &fillerRatio, &asrConfidence, &rawMetrics, &item.CreatedAt, &durationMS, &wordsCount, &meanPauseMS, &totalPauseMS, &fillerCount)
	if err != nil {
		return SpeechMetrics{}, mapError(err)
	}
	item.AudioAssetID = nullableString(audioAssetID)
	if durationMS.Valid {
		value := int(durationMS.Int64)
		item.DurationMS = &value
	}
	if wordsCount.Valid {
		value := int(wordsCount.Int64)
		item.WordsCount = &value
	}
	item.WPM = nullableFloat(wpm)
	if longPauseCount.Valid {
		value := int(longPauseCount.Int64)
		item.LongPauseCount = &value
	}
	item.MeanPauseMS = nullableFloat(meanPauseMS)
	if totalPauseMS.Valid {
		value := int(totalPauseMS.Int64)
		item.TotalPauseMS = &value
	}
	if fillerCount.Valid {
		value := int(fillerCount.Int64)
		item.FillerCount = &value
	}
	item.FillerRatio = nullableFloat(fillerRatio)
	item.ASRConfidence = nullableFloat(asrConfidence)
	item.RawMetrics = json.RawMessage(defaultJSON(rawMetrics, "{}"))
	return item, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	return &value.String
}

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	return &value.Time
}

func nullableFloat(value sql.NullFloat64) *float64 {
	if !value.Valid {
		return nil
	}
	return &value.Float64
}

func defaultJSON(value []byte, fallback string) []byte {
	if len(value) == 0 {
		return []byte(fallback)
	}
	return value
}
