package questionbank

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

func (s PostgresStore) RecordAdminAudit(ctx context.Context, input AdminAuditInput) error {
	metadata, err := marshalMetadata(input.Metadata)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `
		insert into admin_audit_logs
			(actor_user_id, actor_role, action, resource, method, path, status_code, metadata)
		values
			(nullif($1, '')::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb)
	`, input.ActorUserID, input.ActorRole, input.Action, input.Resource, input.Method, input.Path, input.StatusCode, metadata)
	return mapPostgresError(err)
}

func (s PostgresStore) CreateSeason(ctx context.Context, input SeasonInput) (Season, error) {
	input = normalizeSeasonInput(input)
	row := s.db.QueryRowContext(ctx, `
		insert into seasons (code, title, starts_on, ends_on, status)
		values ($1, $2, $3::date, $4::date, $5::content_status)
		returning id::text, code, title, starts_on, ends_on, status::text, is_active, created_at, updated_at, deleted_at
	`, input.Code, input.Title, input.StartsOn, input.EndsOn, input.Status)

	season, err := scanSeason(row)
	if err != nil {
		return Season{}, mapPostgresError(err)
	}
	return season, nil
}

func (s PostgresStore) ListSeasons(ctx context.Context, includeArchived bool) ([]Season, error) {
	query := `
		select id::text, code, title, starts_on, ends_on, status::text, is_active, created_at, updated_at, deleted_at
		from seasons
		where deleted_at is null`
	if !includeArchived {
		query += ` and status <> 'archived'`
	}
	query += ` order by is_active desc, starts_on desc nulls last, created_at desc`

	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	return scanSeasons(rows)
}

func (s PostgresStore) GetActiveSeason(ctx context.Context) (Season, error) {
	return scanSeason(s.db.QueryRowContext(ctx, `
		select id::text, code, title, starts_on, ends_on, status::text, is_active, created_at, updated_at, deleted_at
		from seasons
		where is_active = true and status = 'active' and deleted_at is null
		limit 1
	`))
}

func (s PostgresStore) UpdateSeason(ctx context.Context, id string, input SeasonInput) (Season, error) {
	input = normalizeSeasonInput(input)
	season, err := scanSeason(s.db.QueryRowContext(ctx, `
		update seasons
		set code = $2, title = $3, starts_on = $4::date, ends_on = $5::date, status = $6::content_status
		where id = $1::uuid and deleted_at is null
		returning id::text, code, title, starts_on, ends_on, status::text, is_active, created_at, updated_at, deleted_at
	`, id, input.Code, input.Title, input.StartsOn, input.EndsOn, input.Status))
	if err != nil {
		return Season{}, mapPostgresError(err)
	}
	return season, nil
}

func (s PostgresStore) ActivateSeason(ctx context.Context, id string) (Season, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Season{}, err
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(ctx, `update seasons set is_active = false where is_active = true`); err != nil {
		return Season{}, err
	}

	season, err := scanSeason(tx.QueryRowContext(ctx, `
		update seasons
		set status = 'active', is_active = true
		where id = $1::uuid and deleted_at is null
		returning id::text, code, title, starts_on, ends_on, status::text, is_active, created_at, updated_at, deleted_at
	`, id))
	if err != nil {
		return Season{}, mapPostgresError(err)
	}

	if err := tx.Commit(); err != nil {
		return Season{}, err
	}

	return season, nil
}

func (s PostgresStore) ArchiveSeason(ctx context.Context, id string) error {
	return archiveByID(ctx, s.db, "seasons", id, "status = 'archived', is_active = false, deleted_at = now()")
}

func (s PostgresStore) CreateTopic(ctx context.Context, input TopicInput) (Topic, error) {
	input = normalizeTopicInput(input)
	topic, err := scanTopic(s.db.QueryRowContext(ctx, `
		insert into topics (category_id, name, slug, status)
		values ($1::uuid, $2, $3, $4::content_status)
		returning id::text, category_id::text, name, slug, status::text, created_at, updated_at, deleted_at
	`, input.CategoryID, input.Name, input.Slug, input.Status))
	if err != nil {
		return Topic{}, mapPostgresError(err)
	}
	return topic, nil
}

func (s PostgresStore) ListTopics(ctx context.Context, includeDraft bool) ([]Topic, error) {
	query := `
		select id::text, category_id::text, name, slug, status::text, created_at, updated_at, deleted_at
		from topics
		where deleted_at is null`
	if !includeDraft {
		query += ` and status = 'active'`
	}
	query += ` order by name asc`

	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	topics := []Topic{}
	for rows.Next() {
		topic, err := scanTopic(rows)
		if err != nil {
			return nil, err
		}
		topics = append(topics, topic)
	}
	return topics, rows.Err()
}

func (s PostgresStore) UpdateTopic(ctx context.Context, id string, input TopicInput) (Topic, error) {
	input = normalizeTopicInput(input)
	topic, err := scanTopic(s.db.QueryRowContext(ctx, `
		update topics
		set category_id = $2::uuid, name = $3, slug = $4, status = $5::content_status
		where id = $1::uuid and deleted_at is null
		returning id::text, category_id::text, name, slug, status::text, created_at, updated_at, deleted_at
	`, id, input.CategoryID, input.Name, input.Slug, input.Status))
	if err != nil {
		return Topic{}, mapPostgresError(err)
	}
	return topic, nil
}

func (s PostgresStore) ArchiveTopic(ctx context.Context, id string) error {
	return archiveByID(ctx, s.db, "topics", id, "status = 'archived', deleted_at = now()")
}

func (s PostgresStore) CreateQuestion(ctx context.Context, input QuestionInput, createdBy string) (Question, error) {
	input = normalizeQuestionInput(input)
	if err := validateQuestionInput(input); err != nil {
		return Question{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Question{}, err
	}
	defer tx.Rollback()

	metadata, err := marshalMetadata(input.Metadata)
	if err != nil {
		return Question{}, err
	}

	question, err := scanQuestion(tx.QueryRowContext(ctx, `
		insert into questions (season_id, topic_id, part, text, difficulty, source_type, license, review_status, metadata, created_by)
		values ($1::uuid, $2::uuid, $3, $4, $5, $6::source_type, $7, $8::content_status, $9::jsonb, nullif($10, '')::uuid)
		returning id::text, season_id::text, topic_id::text, part, text, difficulty, source_type::text, license,
			review_status::text, metadata, created_by::text, created_at, updated_at, deleted_at
	`, input.SeasonID, input.TopicID, input.Part, input.Text, input.Difficulty, input.SourceType, input.License, input.ReviewStatus, metadata, createdBy))
	if err != nil {
		return Question{}, mapPostgresError(err)
	}

	if err := replaceQuestionDetails(ctx, tx, question.ID, input); err != nil {
		return Question{}, err
	}

	if err := tx.Commit(); err != nil {
		return Question{}, err
	}

	return s.GetQuestion(ctx, question.ID)
}

func (s PostgresStore) ListQuestions(ctx context.Context, filter QuestionFilter) ([]Question, error) {
	filter = normalizeQuestionFilter(filter)
	args := []any{}
	conditions := []string{"q.deleted_at is null"}

	if filter.SeasonID != "" {
		args = append(args, filter.SeasonID)
		conditions = append(conditions, fmt.Sprintf("q.season_id = $%d::uuid", len(args)))
	}
	if filter.TopicID != "" {
		args = append(args, filter.TopicID)
		conditions = append(conditions, fmt.Sprintf("q.topic_id = $%d::uuid", len(args)))
	}
	if filter.Part != nil {
		args = append(args, *filter.Part)
		conditions = append(conditions, fmt.Sprintf("q.part = $%d", len(args)))
	}
	if filter.ReviewStatus != "" {
		args = append(args, filter.ReviewStatus)
		conditions = append(conditions, fmt.Sprintf("q.review_status = $%d::content_status", len(args)))
	} else if !filter.IncludeDraft {
		conditions = append(conditions, "q.review_status = 'active'")
	}

	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select q.id::text, q.season_id::text, q.topic_id::text, q.part, q.text, q.difficulty,
			q.source_type::text, q.license, q.review_status::text, q.metadata, q.created_by::text,
			q.created_at, q.updated_at, q.deleted_at
		from questions q
		where %s
		order by q.part asc, q.created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	questions := []Question{}
	for rows.Next() {
		question, err := scanQuestion(rows)
		if err != nil {
			return nil, err
		}
		questions = append(questions, question)
	}
	return questions, rows.Err()
}

func (s PostgresStore) GetQuestion(ctx context.Context, id string) (Question, error) {
	question, err := scanQuestion(s.db.QueryRowContext(ctx, `
		select id::text, season_id::text, topic_id::text, part, text, difficulty,
			source_type::text, license, review_status::text, metadata, created_by::text,
			created_at, updated_at, deleted_at
		from questions
		where id = $1::uuid and deleted_at is null
	`, id))
	if err != nil {
		return Question{}, mapPostgresError(err)
	}

	if err := s.loadQuestionDetails(ctx, &question); err != nil {
		return Question{}, err
	}

	return question, nil
}

func (s PostgresStore) UpdateQuestion(ctx context.Context, id string, input QuestionInput, changedBy string) (Question, error) {
	input = normalizeQuestionInput(input)
	if err := validateQuestionInput(input); err != nil {
		return Question{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Question{}, err
	}
	defer tx.Rollback()

	current, err := s.GetQuestion(ctx, id)
	if err != nil {
		return Question{}, err
	}
	snapshot, _ := json.Marshal(current)
	if _, err := tx.ExecContext(ctx, `
		insert into question_versions (question_id, version, snapshot, changed_by)
		values (
			$1::uuid,
			coalesce((select max(version) + 1 from question_versions where question_id = $1::uuid), 1),
			$2::jsonb,
			nullif($3, '')::uuid
		)
	`, id, snapshot, changedBy); err != nil {
		return Question{}, err
	}

	metadata, err := marshalMetadata(input.Metadata)
	if err != nil {
		return Question{}, err
	}

	if _, err := tx.ExecContext(ctx, `
		update questions
		set season_id = $2::uuid, topic_id = $3::uuid, part = $4, text = $5, difficulty = $6,
			source_type = $7::source_type, license = $8, review_status = $9::content_status, metadata = $10::jsonb
		where id = $1::uuid and deleted_at is null
	`, id, input.SeasonID, input.TopicID, input.Part, input.Text, input.Difficulty, input.SourceType, input.License, input.ReviewStatus, metadata); err != nil {
		return Question{}, mapPostgresError(err)
	}

	if err := replaceQuestionDetails(ctx, tx, id, input); err != nil {
		return Question{}, err
	}

	if err := tx.Commit(); err != nil {
		return Question{}, err
	}

	return s.GetQuestion(ctx, id)
}

func (s PostgresStore) ArchiveQuestion(ctx context.Context, id string) error {
	return archiveByID(ctx, s.db, "questions", id, "review_status = 'archived', deleted_at = now()")
}

func (s PostgresStore) loadQuestionDetails(ctx context.Context, question *Question) error {
	cue, err := scanCueCard(s.db.QueryRowContext(ctx, `
		select id::text, question_id::text, prompt, coalesce(to_json(bullet_points), '[]'::json)::text,
			preparation_seconds, speaking_seconds, created_at, updated_at
		from cue_cards
		where question_id = $1::uuid
	`, question.ID))
	if err != nil && !errors.Is(err, ErrNotFound) {
		return err
	}
	if err == nil {
		question.CueCard = &cue
	}

	rows, err := s.db.QueryContext(ctx, `
		select id::text, question_id::text, part, text, trigger_hint, sort_order, review_status::text, created_at, updated_at
		from followup_templates
		where question_id = $1::uuid
		order by sort_order asc, created_at asc
	`, question.ID)
	if err != nil {
		return err
	}
	defer rows.Close()

	followups := []FollowupTemplate{}
	for rows.Next() {
		followup, err := scanFollowup(rows)
		if err != nil {
			return err
		}
		followups = append(followups, followup)
	}
	question.Followups = followups
	return rows.Err()
}

type txExecutor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
}

func replaceQuestionDetails(ctx context.Context, tx txExecutor, questionID string, input QuestionInput) error {
	if _, err := tx.ExecContext(ctx, `delete from cue_cards where question_id = $1::uuid`, questionID); err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `delete from followup_templates where question_id = $1::uuid`, questionID); err != nil {
		return err
	}

	if input.CueCard != nil {
		cue := *input.CueCard
		if cue.PreparationSeconds == 0 {
			cue.PreparationSeconds = 60
		}
		if cue.SpeakingSeconds == 0 {
			cue.SpeakingSeconds = 120
		}

		if _, err := tx.ExecContext(ctx, `
			insert into cue_cards (question_id, prompt, bullet_points, preparation_seconds, speaking_seconds)
			values ($1::uuid, $2, $3, $4, $5)
		`, questionID, cue.Prompt, cue.BulletPoints, cue.PreparationSeconds, cue.SpeakingSeconds); err != nil {
			return err
		}
	}

	for index, followup := range input.Followups {
		followup = normalizeFollowupInput(followup, input.Part, index)
		if _, err := tx.ExecContext(ctx, `
			insert into followup_templates (question_id, part, text, trigger_hint, sort_order, review_status)
			values ($1::uuid, $2, $3, $4, $5, $6::content_status)
		`, questionID, followup.Part, followup.Text, followup.TriggerHint, followup.SortOrder, followup.ReviewStatus); err != nil {
			return err
		}
	}

	return nil
}

func archiveByID(ctx context.Context, db *sql.DB, table string, id string, setClause string) error {
	query := fmt.Sprintf(`update %s set %s where id = $1::uuid and deleted_at is null`, table, setClause)
	result, err := db.ExecContext(ctx, query, id)
	if err != nil {
		return mapPostgresError(err)
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if affected == 0 {
		return ErrNotFound
	}
	return nil
}

func normalizeSeasonInput(input SeasonInput) SeasonInput {
	input.Code = strings.ToUpper(strings.TrimSpace(input.Code))
	input.Title = strings.TrimSpace(input.Title)
	if input.Status == "" {
		input.Status = StatusDraft
	}
	return input
}

func normalizeTopicInput(input TopicInput) TopicInput {
	input.Name = strings.TrimSpace(input.Name)
	input.Slug = strings.ToLower(strings.TrimSpace(input.Slug))
	if input.Status == "" {
		input.Status = StatusDraft
	}
	return input
}

func normalizeQuestionInput(input QuestionInput) QuestionInput {
	input.Text = strings.TrimSpace(input.Text)
	if input.SourceType == "" {
		input.SourceType = SourceOriginal
	}
	if input.ReviewStatus == "" {
		input.ReviewStatus = StatusDraft
	}
	if input.Metadata == nil {
		input.Metadata = map[string]any{}
	}
	return input
}

func normalizeFollowupInput(input FollowupTemplateInput, part int, index int) FollowupTemplateInput {
	if input.Part == 0 {
		input.Part = part
	}
	input.Text = strings.TrimSpace(input.Text)
	if input.SortOrder == 0 {
		input.SortOrder = index
	}
	if input.ReviewStatus == "" {
		input.ReviewStatus = StatusDraft
	}
	return input
}

func normalizeQuestionFilter(filter QuestionFilter) QuestionFilter {
	if filter.Limit <= 0 || filter.Limit > 100 {
		filter.Limit = 50
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func validateQuestionInput(input QuestionInput) error {
	if input.Part == 2 && input.CueCard == nil {
		return fmt.Errorf("%w: Part 2 questions require cue_card", ErrInvalidInput)
	}
	if input.Part != 2 && input.CueCard != nil {
		return fmt.Errorf("%w: cue_card is only allowed for Part 2", ErrInvalidInput)
	}
	return nil
}

func marshalMetadata(metadata map[string]any) ([]byte, error) {
	if metadata == nil {
		metadata = map[string]any{}
	}
	return json.Marshal(metadata)
}

func mapPostgresError(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	if err == nil {
		return nil
	}
	message := err.Error()
	if strings.Contains(message, "duplicate key value") {
		return ErrDuplicateResource
	}
	if strings.Contains(message, "invalid input value for enum") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanSeason(row rowScanner) (Season, error) {
	var season Season
	var startsOn sql.NullTime
	var endsOn sql.NullTime
	var deletedAt sql.NullTime
	err := row.Scan(&season.ID, &season.Code, &season.Title, &startsOn, &endsOn, &season.Status, &season.IsActive, &season.CreatedAt, &season.UpdatedAt, &deletedAt)
	if err != nil {
		return Season{}, mapPostgresError(err)
	}
	season.StartsOn = formatDate(startsOn)
	season.EndsOn = formatDate(endsOn)
	season.DeletedAt = nullableTime(deletedAt)
	return season, nil
}

func scanSeasons(rows *sql.Rows) ([]Season, error) {
	seasons := []Season{}
	for rows.Next() {
		season, err := scanSeason(rows)
		if err != nil {
			return nil, err
		}
		seasons = append(seasons, season)
	}
	return seasons, rows.Err()
}

func scanTopic(row rowScanner) (Topic, error) {
	var topic Topic
	var categoryID sql.NullString
	var deletedAt sql.NullTime
	err := row.Scan(&topic.ID, &categoryID, &topic.Name, &topic.Slug, &topic.Status, &topic.CreatedAt, &topic.UpdatedAt, &deletedAt)
	if err != nil {
		return Topic{}, mapPostgresError(err)
	}
	topic.CategoryID = nullableString(categoryID)
	topic.DeletedAt = nullableTime(deletedAt)
	return topic, nil
}

func scanQuestion(row rowScanner) (Question, error) {
	var question Question
	var seasonID sql.NullString
	var topicID sql.NullString
	var difficulty sql.NullInt64
	var license sql.NullString
	var metadata []byte
	var createdBy sql.NullString
	var deletedAt sql.NullTime
	err := row.Scan(
		&question.ID,
		&seasonID,
		&topicID,
		&question.Part,
		&question.Text,
		&difficulty,
		&question.SourceType,
		&license,
		&question.ReviewStatus,
		&metadata,
		&createdBy,
		&question.CreatedAt,
		&question.UpdatedAt,
		&deletedAt,
	)
	if err != nil {
		return Question{}, mapPostgresError(err)
	}
	question.SeasonID = nullableString(seasonID)
	question.TopicID = nullableString(topicID)
	if difficulty.Valid {
		value := int(difficulty.Int64)
		question.Difficulty = &value
	}
	question.License = nullableString(license)
	if len(metadata) == 0 {
		metadata = []byte(`{}`)
	}
	question.Metadata = json.RawMessage(metadata)
	question.CreatedBy = nullableString(createdBy)
	question.DeletedAt = nullableTime(deletedAt)
	question.Followups = []FollowupTemplate{}
	return question, nil
}

func scanCueCard(row rowScanner) (CueCard, error) {
	var cue CueCard
	var bulletPointsRaw string
	err := row.Scan(&cue.ID, &cue.QuestionID, &cue.Prompt, &bulletPointsRaw, &cue.PreparationSeconds, &cue.SpeakingSeconds, &cue.CreatedAt, &cue.UpdatedAt)
	if err != nil {
		return CueCard{}, mapPostgresError(err)
	}
	if err := json.Unmarshal([]byte(bulletPointsRaw), &cue.BulletPoints); err != nil {
		return CueCard{}, err
	}
	return cue, nil
}

func scanFollowup(row rowScanner) (FollowupTemplate, error) {
	var followup FollowupTemplate
	var questionID sql.NullString
	var triggerHint sql.NullString
	err := row.Scan(&followup.ID, &questionID, &followup.Part, &followup.Text, &triggerHint, &followup.SortOrder, &followup.ReviewStatus, &followup.CreatedAt, &followup.UpdatedAt)
	if err != nil {
		return FollowupTemplate{}, mapPostgresError(err)
	}
	followup.QuestionID = nullableString(questionID)
	followup.TriggerHint = nullableString(triggerHint)
	return followup, nil
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

func formatDate(value sql.NullTime) *string {
	if !value.Valid {
		return nil
	}
	formatted := value.Time.Format("2006-01-02")
	return &formatted
}
