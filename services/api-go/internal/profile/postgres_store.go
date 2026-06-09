package profile

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

func (s PostgresStore) GetBackground(ctx context.Context, userID string) (Background, error) {
	profile, err := ensureUserProfile(ctx, s.db, userID, nil)
	if err != nil {
		return Background{}, err
	}

	questionnaire, err := getLatestQuestionnaire(ctx, s.db, userID)
	if err != nil {
		return Background{}, err
	}

	facts := []BackgroundFact{}
	if questionnaire != nil {
		facts, err = listFacts(ctx, s.db, userID, questionnaire.ID)
		if err != nil {
			return Background{}, err
		}
	}

	return Background{
		Profile:       profile,
		Questionnaire: questionnaire,
		Facts:         facts,
		AgentFacts:    filterAgentFacts(facts),
	}, nil
}

func (s PostgresStore) SaveBackground(ctx context.Context, userID string, input BackgroundInput) (Background, error) {
	input = normalizeBackgroundInput(input)
	if err := validateBackgroundInput(input); err != nil {
		return Background{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Background{}, err
	}
	defer tx.Rollback()

	if _, err := ensureUserProfile(ctx, tx, userID, input.Profile); err != nil {
		return Background{}, err
	}

	existing, err := getLatestQuestionnaire(ctx, tx, userID)
	if err != nil {
		return Background{}, err
	}

	questionnaire, err := upsertQuestionnaire(ctx, tx, userID, existing, input)
	if err != nil {
		return Background{}, err
	}

	if input.Facts != nil {
		if err := replaceFacts(ctx, tx, userID, questionnaire.ID, input); err != nil {
			return Background{}, err
		}
	}

	if err := tx.Commit(); err != nil {
		return Background{}, err
	}

	return s.GetBackground(ctx, userID)
}

type dbQuerier interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
	QueryContext(ctx context.Context, query string, args ...any) (*sql.Rows, error)
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
}

func ensureUserProfile(ctx context.Context, db dbQuerier, userID string, input *ProfileInput) (UserProfile, error) {
	if input == nil {
		if _, err := db.ExecContext(ctx, `
			insert into user_profiles (user_id)
			values ($1::uuid)
			on conflict (user_id) do nothing
		`, userID); err != nil {
			return UserProfile{}, mapError(err)
		}
		return scanUserProfile(db.QueryRowContext(ctx, profileSelectSQL()+` where user_id = $1::uuid and deleted_at is null`, userID))
	}

	displayName := nullableText(input.DisplayName)
	timezone := strings.TrimSpace(input.Timezone)
	if timezone == "" {
		timezone = DefaultTimezone
	}

	return scanUserProfile(db.QueryRowContext(ctx, `
		insert into user_profiles (user_id, display_name, timezone, target_band, current_band, preferred_exam_date)
		values ($1::uuid, $2, $3, $4, $5, $6::date)
		on conflict (user_id) do update set
			display_name = excluded.display_name,
			timezone = excluded.timezone,
			target_band = excluded.target_band,
			current_band = excluded.current_band,
			preferred_exam_date = excluded.preferred_exam_date,
			updated_at = now()
		returning id::text, user_id::text, display_name, timezone, target_band::float8, current_band::float8,
			preferred_exam_date::text, created_at, updated_at, deleted_at
	`, userID, displayName, timezone, input.TargetBand, input.CurrentBand, input.PreferredExamDate))
}

func getLatestQuestionnaire(ctx context.Context, db dbQuerier, userID string) (*Questionnaire, error) {
	item, err := scanQuestionnaire(db.QueryRowContext(ctx, `
		select id::text, user_id::text, version, answers, privacy_exclusions, submitted_at, created_at, updated_at
		from background_questionnaires
		where user_id = $1::uuid
		order by created_at desc
		limit 1
	`, userID))
	if errors.Is(err, ErrNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &item, nil
}

func upsertQuestionnaire(ctx context.Context, db dbQuerier, userID string, existing *Questionnaire, input BackgroundInput) (Questionnaire, error) {
	version := input.Version
	answers := mapToRawJSON(input.Answers)
	exclusions := input.PrivacyExclusions

	if existing != nil {
		if version <= 0 {
			version = existing.Version
		}
		if input.Answers == nil {
			answers = existing.Answers
		}
		if input.PrivacyExclusions == nil {
			exclusions = existing.PrivacyExclusions
		}
	}

	if version <= 0 {
		version = 1
	}
	if answers == nil {
		answers = json.RawMessage(`{}`)
	}
	if exclusions == nil {
		exclusions = []string{}
	}

	privacyJSON, err := json.Marshal(exclusions)
	if err != nil {
		return Questionnaire{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
	}

	if existing == nil {
		return scanQuestionnaire(db.QueryRowContext(ctx, `
			insert into background_questionnaires (user_id, version, answers, privacy_exclusions, submitted_at)
			values ($1::uuid, $2, $3::jsonb, $4::jsonb, case when $5 then now() else null end)
			returning id::text, user_id::text, version, answers, privacy_exclusions, submitted_at, created_at, updated_at
		`, userID, version, []byte(answers), privacyJSON, input.Submitted))
	}

	return scanQuestionnaire(db.QueryRowContext(ctx, `
		update background_questionnaires
		set version = $2,
			answers = $3::jsonb,
			privacy_exclusions = $4::jsonb,
			submitted_at = case when $5 then now() else submitted_at end
		where id = $1::uuid and user_id = $6::uuid
		returning id::text, user_id::text, version, answers, privacy_exclusions, submitted_at, created_at, updated_at
	`, existing.ID, version, []byte(answers), privacyJSON, input.Submitted, userID))
}

func replaceFacts(ctx context.Context, db dbQuerier, userID string, questionnaireID string, input BackgroundInput) error {
	if _, err := db.ExecContext(ctx, `
		delete from background_facts
		where user_id = $1::uuid and questionnaire_id = $2::uuid
	`, userID, questionnaireID); err != nil {
		return mapError(err)
	}

	exclusions := privacyExclusionSet(input.PrivacyExclusions)
	for _, item := range input.Facts {
		item = normalizeFactInput(item)
		allowedUsage, err := json.Marshal(item.AllowedUsage)
		if err != nil {
			return fmt.Errorf("%w: %v", ErrInvalidInput, err)
		}

		isExcluded := item.IsExcluded || factExcluded(item, exclusions)
		if _, err := db.ExecContext(ctx, `
			insert into background_facts (user_id, questionnaire_id, topic, fact_key, fact_value, privacy_level, allowed_usage, is_excluded)
			values ($1::uuid, $2::uuid, $3, $4, $5, $6, ARRAY(select jsonb_array_elements_text($7::jsonb)), $8)
		`, userID, questionnaireID, nullableText(item.Topic), item.FactKey, item.FactValue, item.PrivacyLevel, allowedUsage, isExcluded); err != nil {
			return mapError(err)
		}
	}
	return nil
}

func listFacts(ctx context.Context, db dbQuerier, userID string, questionnaireID string) ([]BackgroundFact, error) {
	rows, err := db.QueryContext(ctx, `
		select id::text, user_id::text, questionnaire_id::text, topic, fact_key, fact_value, privacy_level,
			to_json(allowed_usage), is_excluded, created_at, updated_at
		from background_facts
		where user_id = $1::uuid and questionnaire_id = $2::uuid
		order by created_at asc
	`, userID, questionnaireID)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []BackgroundFact{}
	for rows.Next() {
		item, err := scanFact(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func normalizeBackgroundInput(input BackgroundInput) BackgroundInput {
	input.PrivacyExclusions = normalizeStringList(input.PrivacyExclusions)
	for index := range input.Facts {
		input.Facts[index] = normalizeFactInput(input.Facts[index])
	}
	return input
}

func normalizeFactInput(input FactInput) FactInput {
	input.FactKey = strings.TrimSpace(input.FactKey)
	input.FactValue = strings.TrimSpace(input.FactValue)
	if input.Topic != nil {
		value := strings.TrimSpace(*input.Topic)
		if value == "" {
			input.Topic = nil
		} else {
			input.Topic = &value
		}
	}
	input.PrivacyLevel = strings.TrimSpace(input.PrivacyLevel)
	if input.PrivacyLevel == "" {
		input.PrivacyLevel = PrivacyNormal
	}
	input.AllowedUsage = normalizeStringList(input.AllowedUsage)
	if len(input.AllowedUsage) == 0 {
		input.AllowedUsage = []string{UsageQuestionPersonalization, UsageFeedbackPersonalization}
	}
	return input
}

func validateBackgroundInput(input BackgroundInput) error {
	for _, item := range input.Facts {
		if item.FactKey == "" || item.FactValue == "" {
			return ErrInvalidInput
		}
		if item.PrivacyLevel != PrivacyNormal && item.PrivacyLevel != PrivacySensitive && item.PrivacyLevel != PrivacyPrivate {
			return ErrInvalidInput
		}
		for _, usage := range item.AllowedUsage {
			switch usage {
			case UsageQuestionPersonalization, UsageFeedbackPersonalization, UsageScoringContext:
			default:
				return ErrInvalidInput
			}
		}
	}
	return nil
}

func normalizeStringList(values []string) []string {
	if values == nil {
		return nil
	}
	seen := map[string]struct{}{}
	normalized := []string{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	return normalized
}

func privacyExclusionSet(values []string) map[string]struct{} {
	set := map[string]struct{}{}
	for _, value := range values {
		set[value] = struct{}{}
	}
	return set
}

func factExcluded(input FactInput, exclusions map[string]struct{}) bool {
	if _, ok := exclusions[input.FactKey]; ok {
		return true
	}
	if input.Topic != nil {
		if _, ok := exclusions[*input.Topic+"."+input.FactKey]; ok {
			return true
		}
	}
	return false
}

func filterAgentFacts(facts []BackgroundFact) []BackgroundFact {
	filtered := []BackgroundFact{}
	for _, item := range facts {
		if item.IsExcluded {
			continue
		}
		filtered = append(filtered, item)
	}
	return filtered
}

func profileSelectSQL() string {
	return `select id::text, user_id::text, display_name, timezone, target_band::float8, current_band::float8,
		preferred_exam_date::text, created_at, updated_at, deleted_at
		from user_profiles`
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanUserProfile(row rowScanner) (UserProfile, error) {
	var item UserProfile
	var displayName sql.NullString
	var targetBand sql.NullFloat64
	var currentBand sql.NullFloat64
	var preferredExamDate sql.NullString
	var deletedAt sql.NullTime
	err := row.Scan(&item.ID, &item.UserID, &displayName, &item.Timezone, &targetBand, &currentBand, &preferredExamDate, &item.CreatedAt, &item.UpdatedAt, &deletedAt)
	if err != nil {
		return UserProfile{}, mapError(err)
	}
	item.DisplayName = nullableString(displayName)
	item.TargetBand = nullableFloat(targetBand)
	item.CurrentBand = nullableFloat(currentBand)
	item.PreferredExamDate = nullableString(preferredExamDate)
	item.DeletedAt = nullableTime(deletedAt)
	return item, nil
}

func scanQuestionnaire(row rowScanner) (Questionnaire, error) {
	var item Questionnaire
	var answers []byte
	var privacy []byte
	var submittedAt sql.NullTime
	err := row.Scan(&item.ID, &item.UserID, &item.Version, &answers, &privacy, &submittedAt, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return Questionnaire{}, mapError(err)
	}
	item.Answers = json.RawMessage(defaultJSON(answers, "{}"))
	item.PrivacyExclusions = []string{}
	if len(privacy) > 0 {
		if err := json.Unmarshal(privacy, &item.PrivacyExclusions); err != nil {
			return Questionnaire{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
		}
	}
	item.SubmittedAt = nullableTime(submittedAt)
	return item, nil
}

func scanFact(row rowScanner) (BackgroundFact, error) {
	var item BackgroundFact
	var questionnaireID sql.NullString
	var topic sql.NullString
	var allowedUsage []byte
	err := row.Scan(&item.ID, &item.UserID, &questionnaireID, &topic, &item.FactKey, &item.FactValue, &item.PrivacyLevel, &allowedUsage, &item.IsExcluded, &item.CreatedAt, &item.UpdatedAt)
	if err != nil {
		return BackgroundFact{}, mapError(err)
	}
	item.QuestionnaireID = nullableString(questionnaireID)
	item.Topic = nullableString(topic)
	item.AllowedUsage = []string{}
	if len(allowedUsage) > 0 {
		if err := json.Unmarshal(allowedUsage, &item.AllowedUsage); err != nil {
			return BackgroundFact{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
		}
	}
	return item, nil
}

func nullableText(value *string) any {
	if value == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	if trimmed == "" {
		return nil
	}
	return trimmed
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

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	return &value.Time
}

func mapToRawJSON(value map[string]any) json.RawMessage {
	if value == nil {
		return nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return encoded
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
	if strings.Contains(message, "invalid input syntax") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}
