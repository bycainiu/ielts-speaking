package report

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}

func (s PostgresStore) SaveReport(ctx context.Context, userID string, sessionID string, input SaveReportInput) (ScoreReport, error) {
	input.Normalize()
	if err := input.Validate(sessionID); err != nil {
		return ScoreReport{}, err
	}

	rawReport, err := buildRawReportPayload(input)
	if err != nil {
		return ScoreReport{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return ScoreReport{}, err
	}
	defer tx.Rollback()

	if err := ensureSessionOwnership(ctx, tx, userID, sessionID); err != nil {
		return ScoreReport{}, err
	}

	modelRunID, err := nullableExistingModelRunID(ctx, tx, input.ModelRunID)
	if err != nil {
		return ScoreReport{}, err
	}

	var reportID string
	err = tx.QueryRowContext(ctx, `
		insert into score_reports
			(id, session_id, version, status, overall_band, confidence, disclaimer, model_run_id, raw_report)
		values
			(coalesce($1::uuid, gen_random_uuid()), $2::uuid, $3, $4::report_status, $5, $6, $7, $8, $9::jsonb)
		on conflict (session_id, version) do update set
			status = excluded.status,
			overall_band = excluded.overall_band,
			confidence = excluded.confidence,
			disclaimer = excluded.disclaimer,
			model_run_id = excluded.model_run_id,
			raw_report = excluded.raw_report,
			updated_at = now()
		returning id::text
	`, input.ReportID, sessionID, input.Version, input.Status, input.OverallBand, input.Confidence, input.Disclaimer, modelRunID, rawReport).Scan(&reportID)
	if err != nil {
		return ScoreReport{}, mapError(err)
	}

	if err := replaceCriterionScores(ctx, tx, reportID, input.Criteria); err != nil {
		return ScoreReport{}, err
	}
	if err := replaceFeedbackItems(ctx, tx, reportID, input.FeedbackItems); err != nil {
		return ScoreReport{}, err
	}
	if err := replaceReferenceAnswers(ctx, tx, reportID, input.ReferenceAnswers); err != nil {
		return ScoreReport{}, err
	}
	if err := replaceStudyPlans(ctx, tx, userID, reportID, input.NextPracticePlan); err != nil {
		return ScoreReport{}, err
	}
	if input.Status == StatusReady {
		if _, err := tx.ExecContext(ctx, `
			update practice_sessions
			set status = 'completed', completed_at = coalesce(completed_at, now()), updated_at = now()
			where id = $1::uuid and user_id = $2::uuid and deleted_at is null and status in ('created', 'planned', 'in_progress', 'scoring')
		`, sessionID, userID); err != nil {
			return ScoreReport{}, mapError(err)
		}
	}

	if err := tx.Commit(); err != nil {
		return ScoreReport{}, err
	}
	return s.GetLatestReport(ctx, userID, sessionID)
}

func (s PostgresStore) GetLatestReport(ctx context.Context, userID string, sessionID string) (ScoreReport, error) {
	report, err := scanScoreReport(s.db.QueryRowContext(ctx, `
		select sr.id::text, sr.session_id::text, sr.version, sr.status::text,
			sr.overall_band::float8, sr.confidence::float8, sr.disclaimer,
			sr.model_run_id, sr.raw_report, sr.created_at, sr.updated_at
		from score_reports sr
		join practice_sessions ps on ps.id = sr.session_id
		where sr.session_id = $1::uuid and ps.user_id = $2::uuid and ps.deleted_at is null
		order by sr.version desc, sr.created_at desc
		limit 1
	`, sessionID, userID))
	if err != nil {
		return ScoreReport{}, mapError(err)
	}
	if err := s.loadReportDetails(ctx, &report); err != nil {
		return ScoreReport{}, err
	}
	return report, nil
}

func (s PostgresStore) GetLatestReportForAdmin(ctx context.Context, sessionID string) (ScoreReport, error) {
	report, err := scanScoreReport(s.db.QueryRowContext(ctx, `
		select sr.id::text, sr.session_id::text, sr.version, sr.status::text,
			sr.overall_band::float8, sr.confidence::float8, sr.disclaimer,
			sr.model_run_id, sr.raw_report, sr.created_at, sr.updated_at
		from score_reports sr
		join practice_sessions ps on ps.id = sr.session_id
		where sr.session_id = $1::uuid and ps.deleted_at is null
		order by sr.version desc, sr.created_at desc
		limit 1
	`, sessionID))
	if err != nil {
		return ScoreReport{}, mapError(err)
	}
	if err := s.loadReportDetails(ctx, &report); err != nil {
		return ScoreReport{}, err
	}
	return report, nil
}

func (s PostgresStore) ListReports(ctx context.Context, userID string, filter ReportHistoryFilter) ([]ReportHistoryItem, error) {
	filter = normalizeReportHistoryFilter(filter)
	args := []any{userID}
	conditions := []string{"ps.user_id = $1::uuid", "ps.deleted_at is null", "sr.rn = 1"}

	if filter.Mode != "" {
		args = append(args, filter.Mode)
		conditions = append(conditions, fmt.Sprintf("ps.mode = $%d::session_mode", len(args)))
	}
	if filter.SessionID != "" {
		args = append(args, filter.SessionID)
		conditions = append(conditions, fmt.Sprintf("ps.id = $%d::uuid", len(args)))
	}
	if filter.Part != nil {
		args = append(args, *filter.Part)
		conditions = append(conditions, fmt.Sprintf(`exists (
			select 1 from session_parts sp where sp.session_id = ps.id and sp.part = $%d
		)`, len(args)))
	}
	if filter.From != nil {
		args = append(args, *filter.From)
		conditions = append(conditions, fmt.Sprintf("sr.created_at >= $%d", len(args)))
	}
	if filter.To != nil {
		args = append(args, *filter.To)
		conditions = append(conditions, fmt.Sprintf("sr.created_at < $%d", len(args)))
	}

	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		with ranked_reports as (
			select sr.*, row_number() over (
				partition by sr.session_id
				order by sr.version desc, sr.created_at desc
			) as rn
			from score_reports sr
		)
		select
			sr.id::text,
			sr.session_id::text,
			ps.user_id::text,
			ps.mode::text,
			ps.status::text,
			ps.target_part,
			sr.version,
			sr.status::text,
			sr.overall_band::float8,
			sr.confidence::float8,
			coalesce(
				jsonb_object_agg(
					cs.criterion::text,
					jsonb_build_object('band', cs.band::float8, 'confidence', cs.confidence::float8)
				) filter (where cs.id is not null),
				'{}'::jsonb
			) as criteria,
			ps.created_at,
			ps.completed_at,
			sr.created_at,
			sr.updated_at
		from ranked_reports sr
		join practice_sessions ps on ps.id = sr.session_id
		left join criterion_scores cs on cs.report_id = sr.id
		where %s
		group by sr.id, sr.session_id, ps.user_id, ps.mode, ps.status, ps.target_part, sr.version,
			sr.status, sr.overall_band, sr.confidence, ps.created_at, ps.completed_at,
			sr.created_at, sr.updated_at
		order by sr.created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ReportHistoryItem{}
	for rows.Next() {
		item, err := scanReportHistoryItem(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) ListReportsForAdmin(ctx context.Context, filter ReportHistoryFilter) ([]ReportHistoryItem, error) {
	filter = normalizeReportHistoryFilter(filter)
	args := []any{}
	conditions := []string{"ps.deleted_at is null", "sr.rn = 1"}

	if filter.UserID != "" {
		args = append(args, filter.UserID)
		conditions = append(conditions, fmt.Sprintf("ps.user_id = $%d::uuid", len(args)))
	}
	if filter.SessionID != "" {
		args = append(args, filter.SessionID)
		conditions = append(conditions, fmt.Sprintf("ps.id = $%d::uuid", len(args)))
	}
	if filter.Mode != "" {
		args = append(args, filter.Mode)
		conditions = append(conditions, fmt.Sprintf("ps.mode = $%d::session_mode", len(args)))
	}
	if filter.Part != nil {
		args = append(args, *filter.Part)
		conditions = append(conditions, fmt.Sprintf(`exists (
			select 1 from session_parts sp where sp.session_id = ps.id and sp.part = $%d
		)`, len(args)))
	}
	if filter.From != nil {
		args = append(args, *filter.From)
		conditions = append(conditions, fmt.Sprintf("sr.created_at >= $%d", len(args)))
	}
	if filter.To != nil {
		args = append(args, *filter.To)
		conditions = append(conditions, fmt.Sprintf("sr.created_at < $%d", len(args)))
	}

	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		with ranked_reports as (
			select sr.*, row_number() over (
				partition by sr.session_id
				order by sr.version desc, sr.created_at desc
			) as rn
			from score_reports sr
		)
		select
			sr.id::text,
			sr.session_id::text,
			ps.user_id::text,
			ps.mode::text,
			ps.status::text,
			ps.target_part,
			sr.version,
			sr.status::text,
			sr.overall_band::float8,
			sr.confidence::float8,
			coalesce(
				jsonb_object_agg(
					cs.criterion::text,
					jsonb_build_object('band', cs.band::float8, 'confidence', cs.confidence::float8)
				) filter (where cs.id is not null),
				'{}'::jsonb
			) as criteria,
			ps.created_at,
			ps.completed_at,
			sr.created_at,
			sr.updated_at
		from ranked_reports sr
		join practice_sessions ps on ps.id = sr.session_id
		left join criterion_scores cs on cs.report_id = sr.id
		where %s
		group by sr.id, sr.session_id, ps.user_id, ps.mode, ps.status, ps.target_part, sr.version,
			sr.status, sr.overall_band, sr.confidence, ps.created_at, ps.completed_at,
			sr.created_at, sr.updated_at
		order by sr.created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ReportHistoryItem{}
	for rows.Next() {
		item, err := scanReportHistoryItem(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) SubmitReportFeedback(ctx context.Context, userID string, reportID string, input SubmitReportFeedbackInput) (ReportUserFeedback, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return ReportUserFeedback{}, err
	}
	metadata, err := marshalObject(input.Metadata)
	if err != nil {
		return ReportUserFeedback{}, err
	}
	var item ReportUserFeedback
	var targetID sql.NullString
	var comment sql.NullString
	var rawMetadata []byte
	err = s.db.QueryRowContext(ctx, `
		with owned_report as (
			select sr.id, sr.session_id
			from score_reports sr
			join practice_sessions ps on ps.id = sr.session_id
			where sr.id = $1::uuid and ps.user_id = $2::uuid and ps.deleted_at is null
		)
		insert into report_user_feedback
			(report_id, session_id, user_id, target_type, target_id, vote, comment, metadata)
		select id, session_id, $2::uuid, $3, $4::uuid, $5, $6, $7::jsonb
		from owned_report
		returning id::text, report_id::text, session_id::text, user_id::text,
			target_type, target_id::text, vote, comment, metadata, created_at
	`, reportID, userID, input.TargetType, nullableUUID(input.TargetID), input.Vote, input.Comment, metadata).Scan(
		&item.ID,
		&item.ReportID,
		&item.SessionID,
		&item.UserID,
		&item.TargetType,
		&targetID,
		&item.Vote,
		&comment,
		&rawMetadata,
		&item.CreatedAt,
	)
	if err != nil {
		return ReportUserFeedback{}, mapError(err)
	}
	item.TargetID = nullableString(targetID)
	item.Comment = nullableString(comment)
	item.Metadata = json.RawMessage(defaultJSON(rawMetadata, "{}"))
	return item, nil
}

func (s PostgresStore) ListReportFeedback(ctx context.Context, filter ReportFeedbackFilter) ([]ReportUserFeedback, error) {
	filter = normalizeReportFeedbackFilter(filter)
	args := []any{}
	conditions := []string{"1 = 1"}
	if filter.ReportID != "" {
		args = append(args, filter.ReportID)
		conditions = append(conditions, fmt.Sprintf("ruf.report_id = $%d::uuid", len(args)))
	}
	if filter.SessionID != "" {
		args = append(args, filter.SessionID)
		conditions = append(conditions, fmt.Sprintf("ruf.session_id = $%d::uuid", len(args)))
	}
	if filter.TargetType != "" {
		args = append(args, filter.TargetType)
		conditions = append(conditions, fmt.Sprintf("ruf.target_type = $%d", len(args)))
	}
	if filter.Vote != "" {
		args = append(args, filter.Vote)
		conditions = append(conditions, fmt.Sprintf("ruf.vote = $%d", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select id::text, report_id::text, session_id::text, user_id::text,
			target_type, target_id::text, vote, comment, metadata, created_at
		from report_user_feedback ruf
		where %s
		order by created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))
	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()
	items := []ReportUserFeedback{}
	for rows.Next() {
		item, err := scanReportUserFeedback(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func normalizeReportHistoryFilter(filter ReportHistoryFilter) ReportHistoryFilter {
	if filter.Limit <= 0 {
		filter.Limit = 30
	}
	if filter.Limit > 100 {
		filter.Limit = 100
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeReportFeedbackFilter(filter ReportFeedbackFilter) ReportFeedbackFilter {
	if filter.Limit <= 0 {
		filter.Limit = 100
	}
	if filter.Limit > 500 {
		filter.Limit = 500
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func (s PostgresStore) loadReportDetails(ctx context.Context, report *ScoreReport) error {
	criteria, err := s.listCriterionScores(ctx, report.ID)
	if err != nil {
		return err
	}
	report.Criteria = criteria

	feedbackItems, err := s.listFeedbackItems(ctx, report.ID)
	if err != nil {
		return err
	}
	report.FeedbackItems = feedbackItems

	referenceAnswers, err := s.listReferenceAnswers(ctx, report.ID)
	if err != nil {
		return err
	}
	report.ReferenceAnswers = referenceAnswers

	studyPlans, err := s.listStudyPlans(ctx, report.ID)
	if err != nil {
		return err
	}
	report.StudyPlans = studyPlans
	return nil
}

func (s PostgresStore) listCriterionScores(ctx context.Context, reportID string) ([]CriterionScore, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, report_id::text, criterion::text, band::float8, confidence::float8,
			evidence, suggestions, raw_output, created_at
		from criterion_scores
		where report_id = $1::uuid
		order by case criterion::text
			when 'fluency_coherence' then 1
			when 'lexical_resource' then 2
			when 'grammatical_range_accuracy' then 3
			when 'pronunciation' then 4
			else 5
		end
	`, reportID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []CriterionScore{}
	for rows.Next() {
		item, err := scanCriterionScore(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listFeedbackItems(ctx context.Context, reportID string) ([]FeedbackItem, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, report_id::text, category, priority, title, body, evidence_refs, created_at
		from feedback_items
		where report_id = $1::uuid
		order by priority asc, created_at asc
	`, reportID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []FeedbackItem{}
	for rows.Next() {
		item, err := scanFeedbackItem(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listReferenceAnswers(ctx context.Context, reportID string) ([]ReferenceAnswer, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, report_id::text, turn_id::text, band_target::float8, skeleton,
			answer_text, personalization_notes, created_at
		from reference_answers
		where report_id = $1::uuid
		order by created_at asc
	`, reportID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ReferenceAnswer{}
	for rows.Next() {
		item, err := scanReferenceAnswer(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) listStudyPlans(ctx context.Context, reportID string) ([]StudyPlan, error) {
	rows, err := s.db.QueryContext(ctx, `
		select id::text, report_id::text, user_id::text, priority, focus, task,
			due_on::text, status, created_at, updated_at
		from study_plans
		where report_id = $1::uuid
		order by priority asc, created_at asc
	`, reportID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []StudyPlan{}
	for rows.Next() {
		item, err := scanStudyPlan(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

type txExecutor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
}

func ensureSessionOwnership(ctx context.Context, tx txExecutor, userID string, sessionID string) error {
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

func nullableExistingModelRunID(ctx context.Context, tx txExecutor, modelRunID *string) (*string, error) {
	if modelRunID == nil || strings.TrimSpace(*modelRunID) == "" {
		return nil, nil
	}
	var exists bool
	if err := tx.QueryRowContext(ctx, `select exists(select 1 from agent_runs where id = $1)`, *modelRunID).Scan(&exists); err != nil {
		return nil, mapError(err)
	}
	if !exists {
		return nil, nil
	}
	return modelRunID, nil
}

func replaceCriterionScores(ctx context.Context, tx txExecutor, reportID string, criteria map[string]CriterionScoreInput) error {
	if _, err := tx.ExecContext(ctx, `delete from criterion_scores where report_id = $1::uuid`, reportID); err != nil {
		return mapError(err)
	}
	for _, criterion := range requiredCriteria {
		score := criteria[criterion]
		evidence, err := marshalArray(score.Evidence)
		if err != nil {
			return err
		}
		suggestions, err := json.Marshal(score.Suggestions)
		if err != nil {
			return err
		}
		rawOutput, err := marshalObject(score.RawOutput)
		if err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, `
			insert into criterion_scores
				(report_id, criterion, band, confidence, evidence, suggestions, raw_output)
			values
				($1::uuid, $2::scoring_criterion, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb)
		`, reportID, criterion, score.Band, score.Confidence, evidence, suggestions, rawOutput); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func replaceFeedbackItems(ctx context.Context, tx txExecutor, reportID string, items []FeedbackItemInput) error {
	if _, err := tx.ExecContext(ctx, `delete from feedback_items where report_id = $1::uuid`, reportID); err != nil {
		return mapError(err)
	}
	for _, item := range items {
		evidenceRefs, err := marshalArray(item.EvidenceRefs)
		if err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, `
			insert into feedback_items (report_id, category, priority, title, body, evidence_refs)
			values ($1::uuid, $2, $3, $4, $5, $6::jsonb)
		`, reportID, item.Category, item.Priority, item.Title, item.Body, evidenceRefs); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func replaceReferenceAnswers(ctx context.Context, tx txExecutor, reportID string, items []ReferenceAnswerInput) error {
	if _, err := tx.ExecContext(ctx, `delete from reference_answers where report_id = $1::uuid`, reportID); err != nil {
		return mapError(err)
	}
	for _, item := range items {
		skeleton, err := marshalObject(item.Skeleton)
		if err != nil {
			return err
		}
		turnID := nullableUUID(item.TurnID)
		if _, err := tx.ExecContext(ctx, `
			insert into reference_answers
				(report_id, turn_id, band_target, skeleton, answer_text, personalization_notes)
			values
				($1::uuid, $2::uuid, $3, $4::jsonb, $5, $6)
		`, reportID, turnID, item.BandTarget, skeleton, item.AnswerText, item.PersonalizationNotes); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func replaceStudyPlans(ctx context.Context, tx txExecutor, userID string, reportID string, items []StudyPlanInput) error {
	if _, err := tx.ExecContext(ctx, `delete from study_plans where report_id = $1::uuid`, reportID); err != nil {
		return mapError(err)
	}
	for _, item := range items {
		dueOn := nullableDate(item.DueOn)
		if _, err := tx.ExecContext(ctx, `
			insert into study_plans (report_id, user_id, priority, focus, task, due_on)
			values ($1::uuid, $2::uuid, $3, $4, $5, $6::date)
		`, reportID, userID, item.Priority, item.Focus, item.Task, dueOn); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func buildRawReportPayload(input SaveReportInput) ([]byte, error) {
	payload := map[string]any{}
	for key, value := range input.RawReport {
		payload[key] = value
	}
	payload["version"] = input.Version
	payload["status"] = input.Status
	payload["reviewer_notes"] = input.ReviewerNotes
	payload["disclaimer"] = input.Disclaimer
	payload["feedback_items"] = input.FeedbackItems
	payload["reference_answers"] = input.ReferenceAnswers
	payload["next_practice_plan"] = input.NextPracticePlan
	if input.ModelRunID != nil {
		payload["model_run_id"] = *input.ModelRunID
	}
	return json.Marshal(payload)
}

func marshalObject(value map[string]any) ([]byte, error) {
	if value == nil {
		value = map[string]any{}
	}
	return json.Marshal(value)
}

func marshalArray(value []map[string]any) ([]byte, error) {
	if value == nil {
		value = []map[string]any{}
	}
	return json.Marshal(value)
}

var uuidPattern = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)

func nullableUUID(value *string) *string {
	if value == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	if !uuidPattern.MatchString(trimmed) {
		return nil
	}
	return &trimmed
}

func nullableDate(value *string) *string {
	if value == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	if trimmed == "" {
		return nil
	}
	return &trimmed
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanScoreReport(row rowScanner) (ScoreReport, error) {
	var item ScoreReport
	var overallBand sql.NullFloat64
	var confidence sql.NullFloat64
	var modelRunID sql.NullString
	var rawReport []byte
	err := row.Scan(
		&item.ID,
		&item.SessionID,
		&item.Version,
		&item.Status,
		&overallBand,
		&confidence,
		&item.Disclaimer,
		&modelRunID,
		&rawReport,
		&item.CreatedAt,
		&item.UpdatedAt,
	)
	if err != nil {
		return ScoreReport{}, mapError(err)
	}
	item.OverallBand = nullableFloat(overallBand)
	item.Confidence = nullableFloat(confidence)
	item.ModelRunID = nullableString(modelRunID)
	item.RawReport = json.RawMessage(defaultJSON(rawReport, "{}"))
	item.Criteria = []CriterionScore{}
	item.FeedbackItems = []FeedbackItem{}
	item.ReferenceAnswers = []ReferenceAnswer{}
	item.StudyPlans = []StudyPlan{}
	return item, nil
}

func scanReportHistoryItem(row rowScanner) (ReportHistoryItem, error) {
	var item ReportHistoryItem
	var targetPart sql.NullInt64
	var overallBand sql.NullFloat64
	var confidence sql.NullFloat64
	var criteria []byte
	var completedAt sql.NullTime
	err := row.Scan(
		&item.ID,
		&item.SessionID,
		&item.UserID,
		&item.Mode,
		&item.SessionStatus,
		&targetPart,
		&item.Version,
		&item.ReportStatus,
		&overallBand,
		&confidence,
		&criteria,
		&item.SessionCreatedAt,
		&completedAt,
		&item.ReportCreatedAt,
		&item.ReportUpdatedAt,
	)
	if err != nil {
		return ReportHistoryItem{}, mapError(err)
	}
	item.TargetPart = nullableInt(targetPart)
	item.OverallBand = nullableFloat(overallBand)
	item.Confidence = nullableFloat(confidence)
	item.Criteria = json.RawMessage(defaultJSON(criteria, "{}"))
	item.SessionCompletedAt = nullableTime(completedAt)
	return item, nil
}

func scanCriterionScore(row rowScanner) (CriterionScore, error) {
	var item CriterionScore
	var evidence []byte
	var suggestions []byte
	var rawOutput []byte
	err := row.Scan(&item.ID, &item.ReportID, &item.Criterion, &item.Band, &item.Confidence, &evidence, &suggestions, &rawOutput, &item.CreatedAt)
	if err != nil {
		return CriterionScore{}, mapError(err)
	}
	item.Evidence = json.RawMessage(defaultJSON(evidence, "[]"))
	item.Suggestions = json.RawMessage(defaultJSON(suggestions, "[]"))
	item.RawOutput = json.RawMessage(defaultJSON(rawOutput, "{}"))
	return item, nil
}

func scanFeedbackItem(row rowScanner) (FeedbackItem, error) {
	var item FeedbackItem
	var evidenceRefs []byte
	err := row.Scan(&item.ID, &item.ReportID, &item.Category, &item.Priority, &item.Title, &item.Body, &evidenceRefs, &item.CreatedAt)
	if err != nil {
		return FeedbackItem{}, mapError(err)
	}
	item.EvidenceRefs = json.RawMessage(defaultJSON(evidenceRefs, "[]"))
	return item, nil
}

func scanReferenceAnswer(row rowScanner) (ReferenceAnswer, error) {
	var item ReferenceAnswer
	var turnID sql.NullString
	var bandTarget sql.NullFloat64
	var skeleton []byte
	var personalizationNotes sql.NullString
	err := row.Scan(&item.ID, &item.ReportID, &turnID, &bandTarget, &skeleton, &item.AnswerText, &personalizationNotes, &item.CreatedAt)
	if err != nil {
		return ReferenceAnswer{}, mapError(err)
	}
	item.TurnID = nullableString(turnID)
	item.BandTarget = nullableFloat(bandTarget)
	item.Skeleton = json.RawMessage(defaultJSON(skeleton, "{}"))
	item.PersonalizationNotes = nullableString(personalizationNotes)
	return item, nil
}

func scanStudyPlan(row rowScanner) (StudyPlan, error) {
	var item StudyPlan
	var reportID sql.NullString
	var dueOn sql.NullString
	err := row.Scan(&item.ID, &reportID, &item.UserID, &item.Priority, &item.Focus, &item.Task, &dueOn, &item.Status, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return StudyPlan{}, mapError(err)
	}
	item.ReportID = nullableString(reportID)
	item.DueOn = nullableString(dueOn)
	return item, nil
}

func scanReportUserFeedback(row rowScanner) (ReportUserFeedback, error) {
	var item ReportUserFeedback
	var targetID sql.NullString
	var comment sql.NullString
	var metadata []byte
	err := row.Scan(
		&item.ID,
		&item.ReportID,
		&item.SessionID,
		&item.UserID,
		&item.TargetType,
		&targetID,
		&item.Vote,
		&comment,
		&metadata,
		&item.CreatedAt,
	)
	if err != nil {
		return ReportUserFeedback{}, mapError(err)
	}
	item.TargetID = nullableString(targetID)
	item.Comment = nullableString(comment)
	item.Metadata = json.RawMessage(defaultJSON(metadata, "{}"))
	return item, nil
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	return &value.String
}

func nullableFloat(value sql.NullFloat64) *float64 {
	if !value.Valid {
		return nil
	}
	return &value.Float64
}

func nullableInt(value sql.NullInt64) *int {
	if !value.Valid {
		return nil
	}
	converted := int(value.Int64)
	return &converted
}

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	return &value.Time
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
	if err == nil {
		return nil
	}
	message := err.Error()
	if strings.Contains(message, "invalid input value for enum") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}
