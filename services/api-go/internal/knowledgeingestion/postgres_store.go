package knowledgeingestion

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/ielts-speaking/platform/services/api-go/internal/profile"
)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}

func (s PostgresStore) CreateUpload(ctx context.Context, input CreateUploadRecordInput) (KnowledgeImportJobDetail, error) {
	input = normalizeCreateUploadRecordInput(input)
	if err := validateCreateUploadRecordInput(input); err != nil {
		return KnowledgeImportJobDetail{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	defer tx.Rollback()

	sourceMetadata := copyMetadata(input.SourceMetadata)
	sourceMetadata["requested_action"] = input.RequestedAction
	sourceMetadata["ingestion_status"] = JobStatusQueued

	var fileID string
	if err := tx.QueryRowContext(ctx, `
		insert into knowledge_source_files
			(owner_user_id, visibility, upload_purpose, title, original_filename, extension, mime_type, size_bytes, checksum_sha256, storage_bucket, storage_key, metadata)
		values
			($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
		returning id::text
	`, input.OwnerUserID, input.Visibility, input.Purpose, input.Title, input.OriginalFile, input.Extension, input.MimeType, input.SizeBytes, input.ChecksumSHA256, input.StorageBucket, input.StorageKey, mustJSON(sourceMetadata)).Scan(&fileID); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}

	initialMetadata := map[string]any{
		"source_file_id":           fileID,
		"public_requires_review":   input.Visibility == VisibilityPublic,
		"user_confirmation_needed": input.Visibility == VisibilityPrivate && (input.Purpose == PurposeBackground || input.Purpose == PurposeMixed || input.Purpose == PurposeAuto),
		"materialization_blocked":  input.Visibility == VisibilityPublic || input.Purpose == PurposeBackground,
	}
	status := JobStatusQueued
	stage := "queued"
	var jobID string
	if err := tx.QueryRowContext(ctx, `
		insert into knowledge_ingestion_jobs
			(source_file_id, owner_user_id, requested_visibility, requested_action, status, stage, progress_pct, metadata)
		values
			($1::uuid, $2::uuid, $3, $4, $5, $6, 5, $7::jsonb)
		returning id::text
	`, fileID, input.OwnerUserID, input.Visibility, input.RequestedAction, status, stage, mustJSON(initialMetadata)).Scan(&jobID); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}

	artifactMeta := map[string]any{"source_file_id": fileID}
	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_artifacts
			(job_id, artifact_kind, title, content_type, storage_bucket, storage_key, size_bytes, metadata)
		values
			($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb)
	`, jobID, ArtifactKindOriginal, input.OriginalFile, input.MimeType, input.StorageBucket, input.StorageKey, input.SizeBytes, mustJSON(artifactMeta)); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return KnowledgeImportJobDetail{}, err
	}

	return s.GetJobDetail(ctx, jobID)
}

func (s PostgresStore) ListUserJobs(ctx context.Context, userID string, filter UserJobFilter) ([]KnowledgeImportJobSummary, error) {
	filter = normalizeUserJobFilter(filter)
	args := []any{userID}
	conditions := []string{"j.owner_user_id = $1::uuid"}
	if filter.Status != "" {
		args = append(args, filter.Status)
		conditions = append(conditions, fmt.Sprintf("j.status = $%d", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select
			j.id::text, j.owner_user_id::text, j.requested_visibility, j.requested_action, j.status, j.stage, j.priority,
			j.progress_pct, j.classifier_label, j.classifier_confidence::float8, j.run_id, j.error_code, j.error_message,
			j.duplicate_of_job_id::text, j.queued_at, j.started_at, j.heartbeat_at, j.finished_at, j.materialized_at, j.updated_at, j.metadata,
			sf.id::text, sf.owner_user_id::text, sf.visibility, sf.upload_purpose, sf.title, sf.original_filename,
			sf.extension, sf.mime_type, sf.size_bytes, sf.checksum_sha256, sf.storage_bucket, sf.storage_key, sf.metadata, sf.created_at,
			coalesce(cc.question_count, 0), coalesce(cc.knowledge_count, 0), coalesce(cc.background_count, 0)
		from knowledge_ingestion_jobs j
		join knowledge_source_files sf on sf.id = j.source_file_id
		left join (
			select job_id,
				count(*) filter (where candidate_kind = 'question') as question_count,
				count(*) filter (where candidate_kind = 'knowledge') as knowledge_count,
				count(*) filter (where candidate_kind = 'background') as background_count
			from knowledge_ingestion_candidates
			group by job_id
		) cc on cc.job_id = j.id
		where %s
		order by j.queued_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []KnowledgeImportJobSummary{}
	for rows.Next() {
		item, err := scanJobSummary(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) ListAdminJobs(ctx context.Context, filter AdminJobFilter) ([]KnowledgeImportJobSummary, error) {
	filter = normalizeAdminJobFilter(filter)
	args := []any{}
	conditions := []string{"1 = 1"}
	if filter.Status != "" {
		args = append(args, filter.Status)
		conditions = append(conditions, fmt.Sprintf("j.status = $%d", len(args)))
	}
	if filter.Visibility != "" {
		args = append(args, filter.Visibility)
		conditions = append(conditions, fmt.Sprintf("j.requested_visibility = $%d", len(args)))
	}
	if filter.OwnerUserID != "" {
		args = append(args, filter.OwnerUserID)
		conditions = append(conditions, fmt.Sprintf("j.owner_user_id = $%d::uuid", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select
			j.id::text, j.owner_user_id::text, j.requested_visibility, j.requested_action, j.status, j.stage, j.priority,
			j.progress_pct, j.classifier_label, j.classifier_confidence::float8, j.run_id, j.error_code, j.error_message,
			j.duplicate_of_job_id::text, j.queued_at, j.started_at, j.heartbeat_at, j.finished_at, j.materialized_at, j.updated_at, j.metadata,
			sf.id::text, sf.owner_user_id::text, sf.visibility, sf.upload_purpose, sf.title, sf.original_filename,
			sf.extension, sf.mime_type, sf.size_bytes, sf.checksum_sha256, sf.storage_bucket, sf.storage_key, sf.metadata, sf.created_at,
			coalesce(cc.question_count, 0), coalesce(cc.knowledge_count, 0), coalesce(cc.background_count, 0)
		from knowledge_ingestion_jobs j
		join knowledge_source_files sf on sf.id = j.source_file_id
		left join (
			select job_id,
				count(*) filter (where candidate_kind = 'question') as question_count,
				count(*) filter (where candidate_kind = 'knowledge') as knowledge_count,
				count(*) filter (where candidate_kind = 'background') as background_count
			from knowledge_ingestion_candidates
			group by job_id
		) cc on cc.job_id = j.id
		where %s
		order by j.priority desc, j.queued_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []KnowledgeImportJobSummary{}
	for rows.Next() {
		item, err := scanJobSummary(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) GetJobDetail(ctx context.Context, jobID string) (KnowledgeImportJobDetail, error) {
	summary, err := s.getJobSummary(ctx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}

	candidates, err := s.listCandidates(ctx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	reviews, err := s.listReviews(ctx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	artifacts, err := s.listArtifacts(ctx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}

	var run *KnowledgeImportRunDetail
	if summary.RunID != nil && *summary.RunID != "" {
		runDetail, err := s.getRunDetail(ctx, *summary.RunID)
		if err == nil {
			run = runDetail
		}
	}

	return KnowledgeImportJobDetail{
		KnowledgeImportJobSummary: summary,
		Candidates:                candidates,
		Reviews:                   reviews,
		Artifacts:                 artifacts,
		Run:                       run,
	}, nil
}

func (s PostgresStore) ConfirmBackgroundCandidates(ctx context.Context, userID string, jobID string, input ConfirmBackgroundInput) (KnowledgeImportJobDetail, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	defer tx.Rollback()

	job, err := s.getJobSummaryTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if job.OwnerUserID != userID {
		return KnowledgeImportJobDetail{}, ErrForbidden
	}
	if job.RequestedAction != PurposeBackground && job.RequestedAction != PurposeAuto && job.RequestedAction != PurposeMixed {
		return KnowledgeImportJobDetail{}, ErrConflict
	}
	if job.Status != JobStatusAwaitingUserConfirm {
		return KnowledgeImportJobDetail{}, ErrConflict
	}
	targetIDs := normalizedIDs(input.CandidateIDs)
	if len(targetIDs) == 0 {
		candidates, err := s.listCandidatesTx(ctx, tx, jobID)
		if err != nil {
			return KnowledgeImportJobDetail{}, err
		}
		for _, candidate := range candidates {
			if candidate.CandidateKind == CandidateKindBackground {
				targetIDs = append(targetIDs, candidate.ID)
			}
		}
	}
	if len(targetIDs) == 0 {
		return KnowledgeImportJobDetail{}, ErrInvalidInput
	}

	candidates, err := s.listCandidatesTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	selected := []KnowledgeIngestionCandidate{}
	for _, candidate := range candidates {
		if candidate.CandidateKind != CandidateKindBackground {
			continue
		}
		if containsID(targetIDs, candidate.ID) {
			selected = append(selected, candidate)
		}
	}
	if len(selected) == 0 {
		return KnowledgeImportJobDetail{}, ErrInvalidInput
	}

	if err := materializeBackgroundCandidates(ctx, tx, userID, job.SourceFile.ID, selected); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if err := markCandidatesStatus(ctx, tx, selected, CandidateStatusConfirmed); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_reviews
			(job_id, reviewer_user_id, reviewer_role, decision, payload)
		values
			($1::uuid, $2::uuid, 'user', $3, $4::jsonb)
	`, jobID, userID, ReviewDecisionConfirm, mustJSON(map[string]any{"candidate_ids": targetIDs, "overwrite_existing": input.OverwriteExisting})); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}
	if _, err := tx.ExecContext(ctx, `
		update knowledge_ingestion_jobs
		set status = $2, stage = 'materialized', progress_pct = 100, materialized_at = now(), finished_at = now(), heartbeat_at = now(), metadata = metadata || '{"background_confirmed":true}'::jsonb
		where id = $1::uuid
	`, jobID, JobStatusCompleted); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	return s.GetJobDetail(ctx, jobID)
}

func (s PostgresStore) ReviewJob(ctx context.Context, reviewerUserID string, reviewerRole string, jobID string, input AdminReviewInput) (KnowledgeImportJobDetail, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	defer tx.Rollback()

	job, err := s.getJobSummaryTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if job.RequestedVisibility != VisibilityPublic {
		return KnowledgeImportJobDetail{}, ErrConflict
	}
	if job.Status != JobStatusAwaitingReview {
		return KnowledgeImportJobDetail{}, ErrConflict
	}
	candidates, err := s.listCandidatesTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	targetIDs := normalizedIDs(input.CandidateIDs)
	if len(targetIDs) == 0 {
		for _, candidate := range candidates {
			targetIDs = append(targetIDs, candidate.ID)
		}
	}
	selected := []KnowledgeIngestionCandidate{}
	for _, candidate := range candidates {
		if containsID(targetIDs, candidate.ID) {
			selected = append(selected, candidate)
		}
	}
	if len(selected) == 0 {
		return KnowledgeImportJobDetail{}, ErrInvalidInput
	}

	switch input.Decision {
	case ReviewDecisionApprove:
		if err := materializeApprovedCandidates(ctx, tx, job.OwnerUserID, job.SourceFile.ID, job.RequestedAction, selected, job.SourceFile); err != nil {
			return KnowledgeImportJobDetail{}, err
		}
		if err := markCandidatesStatus(ctx, tx, selected, CandidateStatusApproved); err != nil {
			return KnowledgeImportJobDetail{}, err
		}
		if _, err := tx.ExecContext(ctx, `
			update knowledge_ingestion_jobs
			set status = $2, stage = 'materialized', progress_pct = 100, materialized_at = now(), finished_at = now(), heartbeat_at = now(), metadata = metadata || '{"admin_approved":true}'::jsonb
			where id = $1::uuid
		`, jobID, JobStatusCompleted); err != nil {
			return KnowledgeImportJobDetail{}, mapError(err)
		}
	case ReviewDecisionReject:
		if err := markCandidatesStatus(ctx, tx, selected, CandidateStatusRejected); err != nil {
			return KnowledgeImportJobDetail{}, err
		}
		if _, err := tx.ExecContext(ctx, `
			update knowledge_ingestion_jobs
			set status = $2, stage = 'review_rejected', progress_pct = least(progress_pct, 95), finished_at = now(), heartbeat_at = now(), metadata = metadata || '{"admin_rejected":true}'::jsonb
			where id = $1::uuid
		`, jobID, JobStatusRejected); err != nil {
			return KnowledgeImportJobDetail{}, mapError(err)
		}
	default:
		return KnowledgeImportJobDetail{}, ErrInvalidInput
	}

	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_reviews
			(job_id, reviewer_user_id, reviewer_role, decision, notes, payload)
		values
			($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb)
	`, jobID, reviewerUserID, reviewerRole, input.Decision, nullableStringPointer(strings.TrimSpace(input.Notes)), mustJSON(map[string]any{"candidate_ids": targetIDs})); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	return s.GetJobDetail(ctx, jobID)
}

func (s PostgresStore) CancelJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	defer tx.Rollback()

	job, err := s.getJobSummaryTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if requesterRole != "operator" && requesterRole != "admin" && job.OwnerUserID != requesterUserID {
		return KnowledgeImportJobDetail{}, ErrForbidden
	}
	if _, err := tx.ExecContext(ctx, `
		update knowledge_ingestion_jobs
		set cancel_requested_at = now(),
			status = case when status in ('completed','failed','cancelled','rejected') then status else 'cancelled' end,
			stage = case when status in ('completed','failed','cancelled','rejected') then stage else 'cancel_requested' end,
			finished_at = case when finished_at is null then now() else finished_at end,
			heartbeat_at = now(),
			metadata = metadata || '{"cancel_requested":true}'::jsonb
		where id = $1::uuid
	`, jobID); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}
	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_reviews
			(job_id, reviewer_user_id, reviewer_role, decision, payload)
		values
			($1::uuid, $2::uuid, $3, $4, '{}'::jsonb)
	`, jobID, requesterUserID, requesterRole, ReviewDecisionCancel); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}
	if err := tx.Commit(); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	return s.GetJobDetail(ctx, jobID)
}

func (s PostgresStore) RetryJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	defer tx.Rollback()

	job, err := s.getJobSummaryTx(ctx, tx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if requesterRole != "operator" && requesterRole != "admin" && job.OwnerUserID != requesterUserID {
		return KnowledgeImportJobDetail{}, ErrForbidden
	}
	if _, err := tx.ExecContext(ctx, `
		update knowledge_ingestion_jobs
		set status = 'queued',
			stage = 'queued',
			progress_pct = 5,
			error_code = null,
			error_message = null,
			started_at = null,
			heartbeat_at = now(),
			finished_at = null,
			cancel_requested_at = null,
			metadata = metadata || '{"retry_requested":true}'::jsonb
		where id = $1::uuid
	`, jobID); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}
	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_reviews
			(job_id, reviewer_user_id, reviewer_role, decision, payload)
		values
			($1::uuid, $2::uuid, $3, $4, '{}'::jsonb)
	`, jobID, requesterUserID, requesterRole, ReviewDecisionRetry); err != nil {
		return KnowledgeImportJobDetail{}, mapError(err)
	}
	if err := tx.Commit(); err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	return s.GetJobDetail(ctx, jobID)
}

func (s PostgresStore) GetRuntimePolicy(ctx context.Context) (RuntimePolicy, error) {
	var raw []byte
	var updatedBy sql.NullString
	var updatedAt time.Time
	if err := s.db.QueryRowContext(ctx, `
		select policy_value, updated_by::text, updated_at
		from agent_runtime_policies
		where policy_key = 'document_ingestion'
	`).Scan(&raw, &updatedBy, &updatedAt); err != nil {
		return RuntimePolicy{}, mapError(err)
	}
	payload := map[string]any{}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return RuntimePolicy{}, fmt.Errorf("%w: invalid runtime policy payload", ErrInvalidInput)
	}
	maxConcurrency := intValue(payload["max_concurrency"], 2)
	paused, _ := payload["paused"].(bool)
	return RuntimePolicy{
		PolicyKey:      "document_ingestion",
		MaxConcurrency: maxConcurrency,
		Paused:         paused,
		Raw:            payload,
		UpdatedBy:      nullableString(updatedBy),
		UpdatedAt:      updatedAt,
	}, nil
}

func (s PostgresStore) UpdateRuntimePolicy(ctx context.Context, actorUserID string, input RuntimePolicyUpdateInput) (RuntimePolicy, error) {
	payload := map[string]any{
		"max_concurrency": input.MaxConcurrency,
		"paused":          input.Paused,
	}
	if _, err := s.db.ExecContext(ctx, `
		insert into agent_runtime_policies (policy_key, policy_value, updated_by)
		values ('document_ingestion', $1::jsonb, nullif($2, '')::uuid)
		on conflict (policy_key) do update set
			policy_value = excluded.policy_value,
			updated_by = excluded.updated_by,
			updated_at = now()
	`, mustJSON(payload), actorUserID); err != nil {
		return RuntimePolicy{}, mapError(err)
	}
	return s.GetRuntimePolicy(ctx)
}

func (s PostgresStore) GetArtifact(ctx context.Context, artifactID string) (KnowledgeIngestionArtifact, error) {
	return scanArtifact(s.db.QueryRowContext(ctx, `
		select id::text, job_id::text, run_id, artifact_kind, title, content_type,
			storage_bucket, storage_key, size_bytes, inline_text, metadata, created_at
		from knowledge_ingestion_artifacts
		where id = $1::uuid
	`, artifactID))
}

func bootstrapCandidates(ctx context.Context, tx *sql.Tx, jobID string, fileID string, input CreateUploadRecordInput) ([]KnowledgeIngestionCandidate, error) {
	textSummary := fmt.Sprintf("Imported from %s (%s).", input.OriginalFile, input.MimeType)
	candidates := []struct {
		kind    string
		title   string
		content string
		status  string
		plan    map[string]any
		payload map[string]any
	}{
		{
			kind:    CandidateKindKnowledge,
			title:   input.Title,
			content: textSummary + " Candidate knowledge content preview will be replaced by the document ingestion agent.",
			status:  CandidateStatusPending,
			plan: map[string]any{
				"tables": []string{"knowledge_docs", "knowledge_chunks"},
				"mode":   input.Visibility,
			},
			payload: map[string]any{
				"title":   input.Title,
				"topic":   strings.TrimSpace(input.Title),
				"docType": "topic_knowledge",
			},
		},
	}
	if input.Purpose == PurposeQuestionBank || input.Purpose == PurposeAuto || input.Purpose == PurposeMixed {
		candidates = append(candidates, struct {
			kind    string
			title   string
			content string
			status  string
			plan    map[string]any
			payload map[string]any
		}{
			kind:    CandidateKindQuestion,
			title:   input.Title + " Question Draft",
			content: "Describe a document or article related to " + input.Title,
			status:  CandidateStatusPending,
			plan: map[string]any{
				"tables": []string{"questions", "cue_cards", "followup_templates", "knowledge_docs", "knowledge_chunks"},
				"part":   2,
			},
			payload: map[string]any{
				"part":            2,
				"text":            "Describe a document or article related to " + input.Title,
				"cue_card_prompt": "Describe a document or article related to " + input.Title,
				"bullet_points":   []string{"What it is", "Where you found it", "Why it matters", "And explain what you learned"},
				"followups": []map[string]any{
					{"part": 3, "text": "Why do people rely on written materials to learn new ideas?"},
				},
			},
		})
	}
	if input.Purpose == PurposeBackground || input.Purpose == PurposeAuto || input.Purpose == PurposeMixed {
		status := CandidateStatusPending
		if input.Visibility == VisibilityPrivate {
			status = CandidateStatusPending
		}
		candidates = append(candidates, struct {
			kind    string
			title   string
			content string
			status  string
			plan    map[string]any
			payload map[string]any
		}{
			kind:    CandidateKindBackground,
			title:   input.Title + " Background Facts",
			content: "Potential user background extracted from " + input.OriginalFile,
			status:  status,
			plan: map[string]any{
				"tables": []string{"background_facts", "knowledge_docs", "knowledge_chunks"},
			},
			payload: map[string]any{
				"facts": []map[string]any{
					{"topic": "profile", "fact_key": "document_focus", "fact_value": input.Title, "privacy_level": "normal", "allowed_usage": []string{"question_personalization", "feedback_personalization"}},
				},
			},
		})
	}

	items := make([]KnowledgeIngestionCandidate, 0, len(candidates))
	for _, candidate := range candidates {
		var id string
		if err := tx.QueryRowContext(ctx, `
			insert into knowledge_ingestion_candidates
				(job_id, candidate_kind, title, summary, content, candidate_status, normalized_payload, materialization_plan, metadata)
			values
				($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb)
			returning id::text
		`, jobID, candidate.kind, candidate.title, nullableStringPointer(candidate.content), candidate.content, candidate.status, mustJSON(candidate.payload), mustJSON(candidate.plan), mustJSON(map[string]any{"source_file_id": fileID})).Scan(&id); err != nil {
			return nil, mapError(err)
		}
		items = append(items, KnowledgeIngestionCandidate{
			ID:                  id,
			JobID:               jobID,
			CandidateKind:       candidate.kind,
			Title:               candidate.title,
			Summary:             stringPointer(candidate.content),
			Content:             candidate.content,
			CandidateStatus:     candidate.status,
			NormalizedPayload:   candidate.payload,
			MaterializationPlan: candidate.plan,
			Metadata:            map[string]any{"source_file_id": fileID},
		})
	}

	inlinePreview := "Materialization simulation will be refined by the document ingestion agent."
	if _, err := tx.ExecContext(ctx, `
		insert into knowledge_ingestion_artifacts
			(job_id, artifact_kind, title, content_type, inline_text, metadata)
		values
			($1::uuid, $2, $3, 'text/plain', $4, $5::jsonb)
	`, jobID, ArtifactKindMaterializeSimulate, "Database materialization preview", inlinePreview, mustJSON(map[string]any{"candidate_count": len(items)})); err != nil {
		return nil, mapError(err)
	}
	return items, nil
}

func materializeKnowledgeCandidates(ctx context.Context, tx *sql.Tx, ownerUserID string, sourceFileID string, input CreateUploadRecordInput, candidates []KnowledgeIngestionCandidate) error {
	for _, candidate := range candidates {
		if candidate.CandidateKind != CandidateKindKnowledge {
			continue
		}
		docMetadata := map[string]any{
			"topic":              input.Title,
			"knowledge_type":     "background",
			"source_file_id":     sourceFileID,
			"ingestion_job_hint": candidate.JobID,
		}
		if _, err := insertKnowledgeDocWithChunks(ctx, tx, knowledgeDocInsert{
			DocType:     "topic_knowledge",
			OwnerUserID: &ownerUserID,
			Title:       candidate.Title,
			Content:     candidate.Content,
			Status:      "active",
			Metadata:    docMetadata,
		}); err != nil {
			return err
		}
	}
	return nil
}

func materializeBackgroundCandidates(ctx context.Context, tx *sql.Tx, ownerUserID string, sourceFileID string, candidates []KnowledgeIngestionCandidate) error {
	latest, err := getLatestQuestionnaireSnapshot(ctx, tx, ownerUserID)
	if err != nil {
		return err
	}
	answers := map[string]any{}
	if latest != nil {
		answers = latest.Answers
	}
	questionnaireID, err := insertQuestionnaireSnapshot(ctx, tx, ownerUserID, latest, answers, latestExclusions(latest))
	if err != nil {
		return err
	}
	factsToPersist := []profile.FactInput{}
	for _, candidate := range candidates {
		factsToPersist = append(factsToPersist, backgroundFactsFromCandidate(candidate)...)
	}
	if len(factsToPersist) == 0 {
		return ErrInvalidInput
	}
	if latest != nil {
		for _, fact := range latest.Facts {
			current := profile.FactInput{
				FactKey:      fact.FactKey,
				FactValue:    fact.FactValue,
				PrivacyLevel: fact.PrivacyLevel,
				AllowedUsage: append([]string{}, fact.AllowedUsage...),
				IsExcluded:   fact.IsExcluded,
			}
			if fact.Topic != nil {
				topic := *fact.Topic
				current.Topic = &topic
			}
			factsToPersist = append([]profile.FactInput{current}, factsToPersist...)
		}
	}
	for _, fact := range factsToPersist {
		if _, err := tx.ExecContext(ctx, `
			insert into background_facts (user_id, questionnaire_id, topic, fact_key, fact_value, privacy_level, allowed_usage, is_excluded)
			values ($1::uuid, $2::uuid, $3, $4, $5, $6, ARRAY(select jsonb_array_elements_text($7::jsonb)), $8)
		`, ownerUserID, questionnaireID, nullableStringValue(fact.Topic), fact.FactKey, fact.FactValue, fact.PrivacyLevel, mustJSON(fact.AllowedUsage), fact.IsExcluded); err != nil {
			return mapError(err)
		}
	}

	lines := make([]string, 0, len(factsToPersist))
	for _, fact := range factsToPersist {
		prefix := fact.FactKey
		if fact.Topic != nil && strings.TrimSpace(*fact.Topic) != "" {
			prefix = strings.TrimSpace(*fact.Topic) + "." + fact.FactKey
		}
		lines = append(lines, fmt.Sprintf("%s: %s", prefix, fact.FactValue))
	}
	docMetadata := map[string]any{
		"source_file_id":   sourceFileID,
		"privacy_level":    "normal",
		"allowed_usage":    []string{"question_personalization", "feedback_personalization"},
		"owner_user_id":    ownerUserID,
		"questionnaire_id": questionnaireID,
	}
	if _, err := insertKnowledgeDocWithChunks(ctx, tx, knowledgeDocInsert{
		DocType:     "user_profile",
		OwnerUserID: &ownerUserID,
		Title:       "Imported profile facts",
		Content:     strings.Join(lines, "\n"),
		Status:      "active",
		Metadata:    docMetadata,
	}); err != nil {
		return err
	}
	return nil
}

func backgroundFactsFromCandidate(candidate KnowledgeIngestionCandidate) []profile.FactInput {
	payload := candidate.NormalizedPayload
	items := []profile.FactInput{}
	if rawFacts, ok := payload["facts"].([]any); ok {
		for _, raw := range rawFacts {
			record, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			if fact, ok := backgroundFactFromPayload(record); ok {
				items = append(items, fact)
			}
		}
	}
	if len(items) == 0 {
		if fact, ok := backgroundFactFromPayload(payload); ok {
			items = append(items, fact)
		}
	}
	return items
}

func backgroundFactFromPayload(payload map[string]any) (profile.FactInput, bool) {
	factKey := stringValue(payload["fact_key"])
	factValue := stringValue(payload["fact_value"])
	if factKey == "" || factValue == "" {
		return profile.FactInput{}, false
	}
	privacyLevel := stringValue(payload["privacy_level"])
	if privacyLevel == "" {
		privacyLevel = profile.PrivacyNormal
	}
	allowedUsage := stringList(payload["allowed_usage"])
	if len(allowedUsage) == 0 {
		allowedUsage = []string{profile.UsageQuestionPersonalization, profile.UsageFeedbackPersonalization}
	}
	fact := profile.FactInput{
		FactKey:      factKey,
		FactValue:    factValue,
		PrivacyLevel: privacyLevel,
		AllowedUsage: allowedUsage,
		IsExcluded:   boolValue(payload["is_excluded"]),
	}
	if topic := stringValue(payload["topic"]); topic != "" {
		fact.Topic = &topic
	}
	return fact, true
}

func materializeApprovedCandidates(ctx context.Context, tx *sql.Tx, ownerUserID string, sourceFileID string, requestedAction string, candidates []KnowledgeIngestionCandidate, sourceFile KnowledgeSourceFile) error {
	for _, candidate := range candidates {
		switch candidate.CandidateKind {
		case CandidateKindQuestion:
			part := intValue(candidate.NormalizedPayload["part"], 2)
			text := stringValue(candidate.NormalizedPayload["text"])
			if text == "" {
				text = candidate.Content
			}
			var questionID string
			if err := tx.QueryRowContext(ctx, `
				insert into questions (part, text, source_type, review_status, metadata, created_by)
				values ($1, $2, 'internal'::source_type, 'active'::content_status, $3::jsonb, nullif($4, '')::uuid)
				returning id::text
			`, part, text, mustJSON(map[string]any{"source_file_id": sourceFileID, "ingestion_job_id": candidate.JobID}), ownerUserID).Scan(&questionID); err != nil {
				return mapError(err)
			}
			cuePrompt := stringValue(candidate.NormalizedPayload["cue_card_prompt"])
			bullets := []string{}
			if cuePrompt != "" {
				bullets = stringList(candidate.NormalizedPayload["bullet_points"])
				if _, err := tx.ExecContext(ctx, `
					insert into cue_cards (question_id, prompt, bullet_points, preparation_seconds, speaking_seconds)
					values ($1::uuid, $2, $3, 60, 120)
				`, questionID, cuePrompt, bullets); err != nil {
					return mapError(err)
				}
			}
			followups := followupItems(candidate.NormalizedPayload["followups"])
			for index, item := range followups {
				if _, err := tx.ExecContext(ctx, `
					insert into followup_templates (question_id, part, text, trigger_hint, sort_order, review_status)
					values ($1::uuid, $2, $3, $4, $5, 'active'::content_status)
				`, questionID, intValue(item["part"], 3), stringValue(item["text"]), nullableStringPointer(sourceFile.Title), index); err != nil {
					return mapError(err)
				}
			}
			questionDocContent := buildQuestionDocContent(text, cuePrompt, bullets, followups)
			if _, err := insertKnowledgeDocWithChunks(ctx, tx, knowledgeDocInsert{
				DocType:  "question_bank",
				SourceID: &questionID,
				Title:    candidate.Title,
				Content:  questionDocContent,
				Status:   "active",
				Metadata: map[string]any{"question_id": questionID, "part": fmt.Sprintf("%d", part), "topic": sourceFile.Title, "source_type": "internal"},
			}); err != nil {
				return err
			}
		case CandidateKindKnowledge:
			if _, err := insertKnowledgeDocWithChunks(ctx, tx, knowledgeDocInsert{
				DocType:     "topic_knowledge",
				OwnerUserID: nullableOwnerID(requestedAction, ownerUserID),
				Title:       candidate.Title,
				Content:     candidate.Content,
				Status:      "active",
				Metadata:    map[string]any{"topic": sourceFile.Title, "source_file_id": sourceFileID, "knowledge_type": "background"},
			}); err != nil {
				return err
			}
		case CandidateKindBackground:
			if err := materializeBackgroundCandidates(ctx, tx, ownerUserID, sourceFileID, []KnowledgeIngestionCandidate{candidate}); err != nil {
				return err
			}
		}
	}
	return nil
}

func markCandidatesStatus(ctx context.Context, tx *sql.Tx, candidates []KnowledgeIngestionCandidate, status string) error {
	for _, candidate := range candidates {
		if _, err := tx.ExecContext(ctx, `
			update knowledge_ingestion_candidates
			set candidate_status = $2, updated_at = now()
			where id = $1::uuid
		`, candidate.ID, status); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func (s PostgresStore) getJobSummary(ctx context.Context, jobID string) (KnowledgeImportJobSummary, error) {
	return s.getJobSummaryTx(ctx, s.db, jobID)
}

type querier interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
	QueryContext(context.Context, string, ...any) (*sql.Rows, error)
	ExecContext(context.Context, string, ...any) (sql.Result, error)
}

func (s PostgresStore) getJobSummaryTx(ctx context.Context, q querier, jobID string) (KnowledgeImportJobSummary, error) {
	return scanJobSummary(q.QueryRowContext(ctx, `
		select
			j.id::text, j.owner_user_id::text, j.requested_visibility, j.requested_action, j.status, j.stage, j.priority,
			j.progress_pct, j.classifier_label, j.classifier_confidence::float8, j.run_id, j.error_code, j.error_message,
			j.duplicate_of_job_id::text, j.queued_at, j.started_at, j.heartbeat_at, j.finished_at, j.materialized_at, j.updated_at, j.metadata,
			sf.id::text, sf.owner_user_id::text, sf.visibility, sf.upload_purpose, sf.title, sf.original_filename,
			sf.extension, sf.mime_type, sf.size_bytes, sf.checksum_sha256, sf.storage_bucket, sf.storage_key, sf.metadata, sf.created_at,
			coalesce(cc.question_count, 0), coalesce(cc.knowledge_count, 0), coalesce(cc.background_count, 0)
		from knowledge_ingestion_jobs j
		join knowledge_source_files sf on sf.id = j.source_file_id
		left join (
			select job_id,
				count(*) filter (where candidate_kind = 'question') as question_count,
				count(*) filter (where candidate_kind = 'knowledge') as knowledge_count,
				count(*) filter (where candidate_kind = 'background') as background_count
			from knowledge_ingestion_candidates
			group by job_id
		) cc on cc.job_id = j.id
		where j.id = $1::uuid
	`, jobID))
}

func (s PostgresStore) listCandidates(ctx context.Context, jobID string) ([]KnowledgeIngestionCandidate, error) {
	return s.listCandidatesTx(ctx, s.db, jobID)
}

func (s PostgresStore) listCandidatesTx(ctx context.Context, q querier, jobID string) ([]KnowledgeIngestionCandidate, error) {
	rows, err := q.QueryContext(ctx, `
		select id::text, job_id::text, candidate_kind, title, summary, content, candidate_status, normalized_payload, materialization_plan, metadata, created_at, updated_at
		from knowledge_ingestion_candidates
		where job_id = $1::uuid
		order by created_at asc
	`, jobID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []KnowledgeIngestionCandidate{}
	for rows.Next() {
		item, err := scanCandidate(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listReviews(ctx context.Context, jobID string) ([]KnowledgeIngestionReview, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, job_id::text, candidate_id::text, reviewer_user_id::text, reviewer_role, decision, notes, payload, created_at
		from knowledge_ingestion_reviews
		where job_id = $1::uuid
		order by created_at asc
	`, jobID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []KnowledgeIngestionReview{}
	for rows.Next() {
		item, err := scanReview(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listArtifacts(ctx context.Context, jobID string) ([]KnowledgeIngestionArtifact, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, job_id::text, run_id, artifact_kind, title, content_type, storage_bucket, storage_key, size_bytes, inline_text, metadata, created_at
		from knowledge_ingestion_artifacts
		where job_id = $1::uuid
		order by created_at asc
	`, jobID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []KnowledgeIngestionArtifact{}
	for rows.Next() {
		item, err := scanArtifact(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) getRunDetail(ctx context.Context, runID string) (*KnowledgeImportRunDetail, error) {
	var runKind string
	var subjectType sql.NullString
	var subjectID sql.NullString
	var status string
	var startedAt time.Time
	var finishedAt sql.NullTime
	if err := s.db.QueryRowContext(ctx, `
		select run_kind, subject_type, subject_id, status, started_at, finished_at
		from agent_runs
		where id = $1
	`, runID).Scan(&runKind, &subjectType, &subjectID, &status, &startedAt, &finishedAt); err != nil {
		return nil, mapError(err)
	}
	steps, err := s.listRunSteps(ctx, runID)
	if err != nil {
		return nil, err
	}
	modelCalls, err := s.listRunModelCalls(ctx, runID)
	if err != nil {
		return nil, err
	}
	events, err := s.listRunEvents(ctx, runID)
	if err != nil {
		return nil, err
	}
	artifacts, err := s.listRunArtifacts(ctx, runID)
	if err != nil {
		return nil, err
	}
	return &KnowledgeImportRunDetail{
		RunID:       runID,
		RunKind:     runKind,
		SubjectType: nullableString(subjectType),
		SubjectID:   nullableString(subjectID),
		Status:      status,
		StartedAt:   startedAt,
		FinishedAt:  nullableTime(finishedAt),
		Steps:       steps,
		ModelCalls:  modelCalls,
		Events:      events,
		Artifacts:   artifacts,
	}, nil
}

func (s PostgresStore) listRunSteps(ctx context.Context, runID string) ([]AgentRunStep, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, workflow_node, agent_name, prompt_version, model_name, execution_kind, status,
			input_summary, output_summary, input_payload, input_detail, output_payload, messages, retrieved_chunks,
			structured_output_validity, scoring_result, part, question_id, input_tokens, output_tokens,
			estimated_cost_usd::float8, latency_ms, error_code, error_type, started_at, finished_at
		from agent_steps
		where run_id = $1
		order by started_at asc
	`, runID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []AgentRunStep{}
	for rows.Next() {
		item, err := scanRunStep(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listRunModelCalls(ctx context.Context, runID string) ([]AgentModelCall, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, step_id::text, call_name, agent_name, execution_kind, payload_origin, prompt_version, purpose,
			model_name, status, latency_ms, input_tokens, output_tokens, error_code, output_summary, request_payload, response_payload, created_at
		from model_calls
		where agent_run_id = $1
		order by created_at asc
	`, runID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []AgentModelCall{}
	for rows.Next() {
		item, err := scanModelCall(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listRunEvents(ctx context.Context, runID string) ([]AgentRunEvent, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, step_id::text, event_index, event_type, title, summary, visibility, payload, created_at
		from agent_run_events
		where run_id = $1
		order by event_index asc
	`, runID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []AgentRunEvent{}
	for rows.Next() {
		item, err := scanRunEvent(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listRunArtifacts(ctx context.Context, runID string) ([]AgentRunArtifact, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, step_id::text, artifact_kind, title, content_type, storage_bucket, storage_key, size_bytes, inline_text, metadata, created_at
		from agent_run_artifacts
		where run_id = $1
		order by created_at asc
	`, runID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []AgentRunArtifact{}
	for rows.Next() {
		item, err := scanRunArtifact(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func normalizeCreateUploadRecordInput(input CreateUploadRecordInput) CreateUploadRecordInput {
	input.Visibility = strings.TrimSpace(strings.ToLower(input.Visibility))
	input.Purpose = strings.TrimSpace(strings.ToLower(input.Purpose))
	input.RequestedAction = strings.TrimSpace(strings.ToLower(input.RequestedAction))
	input.Title = strings.TrimSpace(input.Title)
	input.OriginalFile = strings.TrimSpace(input.OriginalFile)
	input.Extension = strings.ToLower(strings.TrimSpace(input.Extension))
	input.MimeType = strings.ToLower(strings.TrimSpace(input.MimeType))
	if input.SourceMetadata == nil {
		input.SourceMetadata = map[string]any{}
	}
	if input.RequestedAction == "" {
		input.RequestedAction = input.Purpose
	}
	return input
}

func validateCreateUploadRecordInput(input CreateUploadRecordInput) error {
	if input.OwnerUserID == "" || input.Visibility == "" || input.Purpose == "" || input.Title == "" || input.OriginalFile == "" || input.Extension == "" || input.MimeType == "" || input.SizeBytes <= 0 || input.ChecksumSHA256 == "" || input.StorageBucket == "" || input.StorageKey == "" {
		return ErrInvalidInput
	}
	switch input.Visibility {
	case VisibilityPrivate, VisibilityPublic:
	default:
		return ErrInvalidInput
	}
	switch input.Purpose {
	case PurposeAuto, PurposeQuestionBank, PurposeKnowledge, PurposeBackground, PurposeMixed:
	default:
		return ErrInvalidInput
	}
	switch input.RequestedAction {
	case PurposeAuto, PurposeQuestionBank, PurposeKnowledge, PurposeBackground, PurposeMixed:
	default:
		return ErrInvalidInput
	}
	return nil
}

func normalizeUserJobFilter(filter UserJobFilter) UserJobFilter {
	filter.Status = strings.TrimSpace(filter.Status)
	if filter.Limit <= 0 {
		filter.Limit = 40
	}
	if filter.Limit > 200 {
		filter.Limit = 200
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeAdminJobFilter(filter AdminJobFilter) AdminJobFilter {
	filter.Status = strings.TrimSpace(filter.Status)
	filter.Visibility = strings.TrimSpace(filter.Visibility)
	filter.OwnerUserID = strings.TrimSpace(filter.OwnerUserID)
	if filter.Limit <= 0 {
		filter.Limit = 80
	}
	if filter.Limit > 200 {
		filter.Limit = 200
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func scanJobSummary(row rowScanner) (KnowledgeImportJobSummary, error) {
	var item KnowledgeImportJobSummary
	var classifierLabel sql.NullString
	var classifierConfidence sql.NullFloat64
	var runID sql.NullString
	var errorCode sql.NullString
	var errorMessage sql.NullString
	var duplicateOf sql.NullString
	var startedAt sql.NullTime
	var heartbeatAt sql.NullTime
	var finishedAt sql.NullTime
	var materializedAt sql.NullTime
	var metadata []byte
	var sourceMetadata []byte
	var questionCount int
	var knowledgeCount int
	var backgroundCount int
	err := row.Scan(
		&item.ID, &item.OwnerUserID, &item.RequestedVisibility, &item.RequestedAction, &item.Status, &item.Stage, &item.Priority,
		&item.ProgressPct, &classifierLabel, &classifierConfidence, &runID, &errorCode, &errorMessage,
		&duplicateOf, &item.QueuedAt, &startedAt, &heartbeatAt, &finishedAt, &materializedAt, &item.UpdatedAt, &metadata,
		&item.SourceFile.ID, &item.SourceFile.OwnerUserID, &item.SourceFile.Visibility, &item.SourceFile.UploadPurpose, &item.SourceFile.Title, &item.SourceFile.OriginalFilename,
		&item.SourceFile.Extension, &item.SourceFile.MimeType, &item.SourceFile.SizeBytes, &item.SourceFile.ChecksumSHA256, &item.SourceFile.StorageBucket, &item.SourceFile.StorageKey, &sourceMetadata, &item.SourceFile.CreatedAt,
		&questionCount, &knowledgeCount, &backgroundCount,
	)
	if err != nil {
		return KnowledgeImportJobSummary{}, mapError(err)
	}
	item.SourceFile.Metadata = unmarshalMap(sourceMetadata)
	item.Metadata = unmarshalMap(metadata)
	item.SourceFile.Metadata = unmarshalMap(sourceMetadata)
	item.ClassifierLabel = nullableString(classifierLabel)
	item.RunID = nullableString(runID)
	item.ErrorCode = nullableString(errorCode)
	item.ErrorMessage = nullableString(errorMessage)
	item.DuplicateOfJobID = nullableString(duplicateOf)
	item.StartedAt = nullableTime(startedAt)
	item.HeartbeatAt = nullableTime(heartbeatAt)
	item.FinishedAt = nullableTime(finishedAt)
	item.MaterializedAt = nullableTime(materializedAt)
	if classifierConfidence.Valid {
		value := classifierConfidence.Float64
		item.ClassifierConfidence = &value
	}
	item.CandidateCounts = map[string]int{
		CandidateKindQuestion:   questionCount,
		CandidateKindKnowledge:  knowledgeCount,
		CandidateKindBackground: backgroundCount,
	}
	return item, nil
}

func scanCandidate(row rowScanner) (KnowledgeIngestionCandidate, error) {
	var item KnowledgeIngestionCandidate
	var summary sql.NullString
	var normalized []byte
	var plan []byte
	var metadata []byte
	if err := row.Scan(&item.ID, &item.JobID, &item.CandidateKind, &item.Title, &summary, &item.Content, &item.CandidateStatus, &normalized, &plan, &metadata, &item.CreatedAt, &item.UpdatedAt); err != nil {
		return KnowledgeIngestionCandidate{}, mapError(err)
	}
	item.Summary = nullableString(summary)
	item.NormalizedPayload = unmarshalMap(normalized)
	item.MaterializationPlan = unmarshalMap(plan)
	item.Metadata = unmarshalMap(metadata)
	return item, nil
}

func scanReview(row rowScanner) (KnowledgeIngestionReview, error) {
	var item KnowledgeIngestionReview
	var candidateID sql.NullString
	var notes sql.NullString
	var payload []byte
	if err := row.Scan(&item.ID, &item.JobID, &candidateID, &item.ReviewerUserID, &item.ReviewerRole, &item.Decision, &notes, &payload, &item.CreatedAt); err != nil {
		return KnowledgeIngestionReview{}, mapError(err)
	}
	item.CandidateID = nullableString(candidateID)
	item.Notes = nullableString(notes)
	item.Payload = unmarshalMap(payload)
	return item, nil
}

func scanArtifact(row rowScanner) (KnowledgeIngestionArtifact, error) {
	var item KnowledgeIngestionArtifact
	var runID sql.NullString
	var storageBucket sql.NullString
	var storageKey sql.NullString
	var sizeBytes sql.NullInt64
	var inlineText sql.NullString
	var metadata []byte
	if err := row.Scan(&item.ID, &item.JobID, &runID, &item.ArtifactKind, &item.Title, &item.ContentType, &storageBucket, &storageKey, &sizeBytes, &inlineText, &metadata, &item.CreatedAt); err != nil {
		return KnowledgeIngestionArtifact{}, mapError(err)
	}
	item.RunID = nullableString(runID)
	item.StorageBucket = nullableString(storageBucket)
	item.StorageKey = nullableString(storageKey)
	if sizeBytes.Valid {
		value := sizeBytes.Int64
		item.SizeBytes = &value
	}
	item.InlineText = nullableString(inlineText)
	item.Metadata = unmarshalMap(metadata)
	return item, nil
}

func scanRunStep(row rowScanner) (AgentRunStep, error) {
	var item AgentRunStep
	var agentName sql.NullString
	var promptVersion sql.NullString
	var modelName sql.NullString
	var executionKind sql.NullString
	var inputSummary sql.NullString
	var outputSummary sql.NullString
	var part sql.NullInt16
	var questionID sql.NullString
	var inputTokens sql.NullInt64
	var outputTokens sql.NullInt64
	var estimatedCost sql.NullFloat64
	var latencyMS sql.NullInt64
	var errorCode sql.NullString
	var errorType sql.NullString
	var finishedAt sql.NullTime
	var inputPayload []byte
	var inputDetail []byte
	var outputPayload []byte
	var messages []byte
	var retrievedChunks []byte
	var scoringResult []byte
	var structured sql.NullBool
	if err := row.Scan(&item.ID, &item.WorkflowNode, &agentName, &promptVersion, &modelName, &executionKind, &item.Status,
		&inputSummary, &outputSummary, &inputPayload, &inputDetail, &outputPayload, &messages, &retrievedChunks,
		&structured, &scoringResult, &part, &questionID, &inputTokens, &outputTokens, &estimatedCost, &latencyMS,
		&errorCode, &errorType, &item.StartedAt, &finishedAt); err != nil {
		return AgentRunStep{}, mapError(err)
	}
	item.AgentName = nullableString(agentName)
	item.PromptVersion = nullableString(promptVersion)
	item.ModelName = nullableString(modelName)
	item.ExecutionKind = nullableString(executionKind)
	item.InputSummary = nullableString(inputSummary)
	item.OutputSummary = nullableString(outputSummary)
	item.InputPayload = unmarshalAny(inputPayload)
	item.InputDetail = unmarshalAny(inputDetail)
	item.OutputPayload = unmarshalAny(outputPayload)
	item.Messages = unmarshalAny(messages)
	item.RetrievedChunks = unmarshalAny(retrievedChunks)
	item.ScoringResult = unmarshalAny(scoringResult)
	item.QuestionID = nullableString(questionID)
	item.ErrorCode = nullableString(errorCode)
	item.ErrorType = nullableString(errorType)
	item.FinishedAt = nullableTime(finishedAt)
	if structured.Valid {
		value := structured.Bool
		item.StructuredOutputValidity = &value
	}
	if part.Valid {
		value := int(part.Int16)
		item.Part = &value
	}
	if inputTokens.Valid {
		value := int(inputTokens.Int64)
		item.InputTokens = &value
	}
	if outputTokens.Valid {
		value := int(outputTokens.Int64)
		item.OutputTokens = &value
	}
	if estimatedCost.Valid {
		value := estimatedCost.Float64
		item.EstimatedCostUSD = &value
	}
	if latencyMS.Valid {
		value := int(latencyMS.Int64)
		item.LatencyMS = &value
	}
	return item, nil
}

func scanModelCall(row rowScanner) (AgentModelCall, error) {
	var item AgentModelCall
	var stepID sql.NullString
	var callName sql.NullString
	var agentName sql.NullString
	var executionKind sql.NullString
	var payloadOrigin sql.NullString
	var promptVersion sql.NullString
	var latencyMS sql.NullInt64
	var inputTokens sql.NullInt64
	var outputTokens sql.NullInt64
	var errorCode sql.NullString
	var outputSummary sql.NullString
	var requestPayload []byte
	var responsePayload []byte
	if err := row.Scan(&item.ID, &stepID, &callName, &agentName, &executionKind, &payloadOrigin, &promptVersion, &item.Purpose, &item.ModelName, &item.Status, &latencyMS, &inputTokens, &outputTokens, &errorCode, &outputSummary, &requestPayload, &responsePayload, &item.CreatedAt); err != nil {
		return AgentModelCall{}, mapError(err)
	}
	item.StepID = nullableString(stepID)
	item.CallName = nullableString(callName)
	item.AgentName = nullableString(agentName)
	item.ExecutionKind = nullableString(executionKind)
	item.PayloadOrigin = nullableString(payloadOrigin)
	item.PromptVersion = nullableString(promptVersion)
	item.ErrorCode = nullableString(errorCode)
	item.OutputSummary = nullableString(outputSummary)
	item.RequestPayload = unmarshalAny(requestPayload)
	item.ResponsePayload = unmarshalAny(responsePayload)
	if latencyMS.Valid {
		value := int(latencyMS.Int64)
		item.LatencyMS = &value
	}
	if inputTokens.Valid {
		value := int(inputTokens.Int64)
		item.InputTokens = &value
	}
	if outputTokens.Valid {
		value := int(outputTokens.Int64)
		item.OutputTokens = &value
	}
	return item, nil
}

func scanRunEvent(row rowScanner) (AgentRunEvent, error) {
	var item AgentRunEvent
	var stepID sql.NullString
	var title sql.NullString
	var summary sql.NullString
	var payload []byte
	if err := row.Scan(&item.ID, &stepID, &item.EventIndex, &item.EventType, &title, &summary, &item.Visibility, &payload, &item.CreatedAt); err != nil {
		return AgentRunEvent{}, mapError(err)
	}
	item.StepID = nullableString(stepID)
	item.Title = nullableString(title)
	item.Summary = nullableString(summary)
	item.Payload = unmarshalMap(payload)
	return item, nil
}

func scanRunArtifact(row rowScanner) (AgentRunArtifact, error) {
	var item AgentRunArtifact
	var stepID sql.NullString
	var storageBucket sql.NullString
	var storageKey sql.NullString
	var sizeBytes sql.NullInt64
	var inlineText sql.NullString
	var metadata []byte
	if err := row.Scan(&item.ID, &stepID, &item.ArtifactKind, &item.Title, &item.ContentType, &storageBucket, &storageKey, &sizeBytes, &inlineText, &metadata, &item.CreatedAt); err != nil {
		return AgentRunArtifact{}, mapError(err)
	}
	item.StepID = nullableString(stepID)
	item.StorageBucket = nullableString(storageBucket)
	item.StorageKey = nullableString(storageKey)
	if sizeBytes.Valid {
		value := sizeBytes.Int64
		item.SizeBytes = &value
	}
	item.InlineText = nullableString(inlineText)
	item.Metadata = unmarshalMap(metadata)
	return item, nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func mapError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	return err
}

func copyMetadata(input map[string]any) map[string]any {
	if input == nil {
		return map[string]any{}
	}
	next := make(map[string]any, len(input))
	for key, value := range input {
		next[key] = value
	}
	return next
}

func mustJSON(value any) string {
	payload, err := json.Marshal(value)
	if err != nil {
		return `{}`
	}
	return string(payload)
}

func unmarshalMap(value []byte) map[string]any {
	if len(value) == 0 {
		return map[string]any{}
	}
	payload := map[string]any{}
	if err := json.Unmarshal(value, &payload); err != nil {
		return map[string]any{}
	}
	return payload
}

func unmarshalAny(value []byte) any {
	if len(value) == 0 {
		return nil
	}
	var payload any
	if err := json.Unmarshal(value, &payload); err != nil {
		return nil
	}
	return payload
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	text := value.String
	return &text
}

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	timestamp := value.Time
	return &timestamp
}

func normalizedIDs(values []string) []string {
	seen := map[string]struct{}{}
	items := []string{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		items = append(items, value)
	}
	return items
}

func containsID(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func nullableStringPointer(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return strings.TrimSpace(value)
}

func stringPointer(value string) *string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	text := strings.TrimSpace(value)
	return &text
}

func stringValue(value any) string {
	if text, ok := value.(string); ok {
		return strings.TrimSpace(text)
	}
	return ""
}

func stringList(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		items := []string{}
		for _, item := range typed {
			if text, ok := item.(string); ok && strings.TrimSpace(text) != "" {
				items = append(items, strings.TrimSpace(text))
			}
		}
		return items
	default:
		return []string{}
	}
}

func intValue(value any, fallback int) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case int:
		return typed
	default:
		return fallback
	}
}

func boolValue(value any) bool {
	typed, _ := value.(bool)
	return typed
}

func hashText(value string) string {
	if strings.TrimSpace(value) == "" {
		value = time.Now().UTC().String()
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return fmt.Sprintf("sha256:%x", sum[:])
}

func nullableOwnerID(requestedAction string, ownerUserID string) *string {
	if requestedAction == PurposeKnowledge || requestedAction == PurposeBackground {
		id := ownerUserID
		return &id
	}
	return nil
}

type questionnaireSnapshot struct {
	ID                string
	Version           int
	Answers           map[string]any
	PrivacyExclusions []string
	Facts             []profile.BackgroundFact
}

type knowledgeDocInsert struct {
	DocType     string
	OwnerUserID *string
	SourceID    *string
	Title       string
	Content     string
	Status      string
	Metadata    map[string]any
}

func insertKnowledgeDocWithChunks(ctx context.Context, tx *sql.Tx, input knowledgeDocInsert) (string, error) {
	metadata := copyMetadata(input.Metadata)
	metadata["doc_type"] = input.DocType
	metadata["status"] = input.Status
	metadata["title"] = input.Title
	var docID string
	if err := tx.QueryRowContext(ctx, `
		insert into knowledge_docs (doc_type, owner_user_id, source_id, title, content_hash, metadata, status)
		values ($1::knowledge_doc_type, nullif($2, '')::uuid, nullif($3, '')::uuid, $4, $5, $6::jsonb, $7::content_status)
		returning id::text
	`, input.DocType, nullableStringOrEmpty(input.OwnerUserID), nullableStringOrEmpty(input.SourceID), input.Title, hashText(input.Content), mustJSON(metadata), input.Status).Scan(&docID); err != nil {
		return "", mapError(err)
	}
	chunks := splitText(input.Content, 1200, 120)
	for index, chunk := range chunks {
		chunkMetadata := copyMetadata(metadata)
		chunkMetadata["chunk_index"] = index
		if _, err := tx.ExecContext(ctx, `
			insert into knowledge_chunks (doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
			values ($1::uuid, $2, $3, $4::jsonb, null, null, $5)
		`, docID, index, chunk, mustJSON(chunkMetadata), estimateTokenCount(chunk)); err != nil {
			return "", mapError(err)
		}
	}
	return docID, nil
}

func getLatestQuestionnaireSnapshot(ctx context.Context, tx *sql.Tx, ownerUserID string) (*questionnaireSnapshot, error) {
	var snapshot questionnaireSnapshot
	var answersBytes []byte
	var exclusionsBytes []byte
	err := tx.QueryRowContext(ctx, `
		select id::text, version, answers, privacy_exclusions
		from background_questionnaires
		where user_id = $1::uuid
		order by created_at desc
		limit 1
	`, ownerUserID).Scan(&snapshot.ID, &snapshot.Version, &answersBytes, &exclusionsBytes)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, mapError(err)
	}
	snapshot.Answers = unmarshalMap(answersBytes)
	if err := json.Unmarshal(exclusionsBytes, &snapshot.PrivacyExclusions); err != nil {
		return nil, fmt.Errorf("%w: invalid privacy exclusions", ErrInvalidInput)
	}
	rows, err := tx.QueryContext(ctx, `
		select id::text, user_id::text, questionnaire_id::text, topic, fact_key, fact_value, privacy_level,
			to_json(allowed_usage), is_excluded, created_at, updated_at
		from background_facts
		where questionnaire_id = $1::uuid
		order by created_at asc
	`, snapshot.ID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	snapshot.Facts = []profile.BackgroundFact{}
	for rows.Next() {
		fact, err := scanBackgroundFact(rows)
		if err != nil {
			return nil, err
		}
		snapshot.Facts = append(snapshot.Facts, fact)
	}
	return &snapshot, rows.Err()
}

func insertQuestionnaireSnapshot(ctx context.Context, tx *sql.Tx, ownerUserID string, latest *questionnaireSnapshot, answers map[string]any, exclusions []string) (string, error) {
	version := 1
	if latest != nil {
		version = latest.Version + 1
	}
	answersJSON, err := json.Marshal(answers)
	if err != nil {
		return "", fmt.Errorf("%w: invalid questionnaire answers", ErrInvalidInput)
	}
	exclusionsJSON, err := json.Marshal(exclusions)
	if err != nil {
		return "", fmt.Errorf("%w: invalid questionnaire exclusions", ErrInvalidInput)
	}
	var questionnaireID string
	if err := tx.QueryRowContext(ctx, `
		insert into background_questionnaires (user_id, version, answers, privacy_exclusions, submitted_at)
		values ($1::uuid, $2, $3::jsonb, $4::jsonb, now())
		returning id::text
	`, ownerUserID, version, answersJSON, exclusionsJSON).Scan(&questionnaireID); err != nil {
		return "", mapError(err)
	}
	return questionnaireID, nil
}

func latestExclusions(latest *questionnaireSnapshot) []string {
	if latest == nil {
		return []string{}
	}
	return append([]string{}, latest.PrivacyExclusions...)
}

func splitText(content string, maxChars int, overlapChars int) []string {
	content = strings.TrimSpace(content)
	if content == "" {
		return []string{"-"}
	}
	if len(content) <= maxChars {
		return []string{content}
	}
	chunks := []string{}
	for start := 0; start < len(content); {
		end := start + maxChars
		if end >= len(content) {
			chunks = append(chunks, strings.TrimSpace(content[start:]))
			break
		}
		cut := end
		if idx := strings.LastIndexAny(content[start:end], "\n.?!; "); idx > maxChars/2 {
			cut = start + idx + 1
		}
		chunks = append(chunks, strings.TrimSpace(content[start:cut]))
		next := cut - overlapChars
		if next <= start {
			next = cut
		}
		start = next
	}
	return chunks
}

func estimateTokenCount(content string) int {
	return len(strings.Fields(content))
}

func nullableStringOrEmpty(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}

func nullableStringValue(value *string) any {
	if value == nil {
		return nil
	}
	text := strings.TrimSpace(*value)
	if text == "" {
		return nil
	}
	return text
}

func scanBackgroundFact(row rowScanner) (profile.BackgroundFact, error) {
	var item profile.BackgroundFact
	var questionnaireID sql.NullString
	var topic sql.NullString
	var allowedUsage []byte
	if err := row.Scan(&item.ID, &item.UserID, &questionnaireID, &topic, &item.FactKey, &item.FactValue, &item.PrivacyLevel, &allowedUsage, &item.IsExcluded, &item.CreatedAt, &item.UpdatedAt); err != nil {
		return profile.BackgroundFact{}, mapError(err)
	}
	item.QuestionnaireID = nullableString(questionnaireID)
	item.Topic = nullableString(topic)
	if len(allowedUsage) > 0 {
		if err := json.Unmarshal(allowedUsage, &item.AllowedUsage); err != nil {
			return profile.BackgroundFact{}, fmt.Errorf("%w: invalid allowed usage", ErrInvalidInput)
		}
	}
	return item, nil
}

func followupItems(value any) []map[string]any {
	switch typed := value.(type) {
	case []map[string]any:
		return typed
	case []any:
		items := []map[string]any{}
		for _, item := range typed {
			record, ok := item.(map[string]any)
			if ok {
				items = append(items, record)
			}
		}
		return items
	default:
		return []map[string]any{}
	}
}

func buildQuestionDocContent(text string, cuePrompt string, bullets []string, followups []map[string]any) string {
	lines := []string{text}
	if cuePrompt != "" {
		lines = append(lines, "Cue card: "+cuePrompt)
	}
	for _, bullet := range bullets {
		lines = append(lines, "- "+bullet)
	}
	for _, followup := range followups {
		lines = append(lines, "Follow-up: "+stringValue(followup["text"]))
	}
	return strings.Join(lines, "\n")
}
