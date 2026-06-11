package report

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	StatusGenerating = "generating"
	StatusReady      = "ready"
	StatusFailed     = "failed"

	IELTSDisclaimer = "AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。"
)

var requiredCriteria = []string{
	"fluency_coherence",
	"lexical_resource",
	"grammatical_range_accuracy",
	"pronunciation",
}

var feedbackTargetTypes = []string{
	"overall",
	"score",
	"feedback",
	"reference_answer",
}

type ScoreReport struct {
	ID               string            `json:"id"`
	SessionID        string            `json:"session_id"`
	Version          int               `json:"version"`
	Status           string            `json:"status"`
	OverallBand      *float64          `json:"overall_band,omitempty"`
	Confidence       *float64          `json:"confidence,omitempty"`
	Disclaimer       string            `json:"disclaimer"`
	ModelRunID       *string           `json:"model_run_id,omitempty"`
	RawReport        json.RawMessage   `json:"raw_report"`
	CreatedAt        time.Time         `json:"created_at"`
	UpdatedAt        time.Time         `json:"updated_at"`
	Criteria         []CriterionScore  `json:"criteria"`
	FeedbackItems    []FeedbackItem    `json:"feedback_items"`
	ReferenceAnswers []ReferenceAnswer `json:"reference_answers"`
	StudyPlans       []StudyPlan       `json:"study_plans"`
}

type ReportHistoryFilter struct {
	Mode      string
	Part      *int
	From      *time.Time
	To        *time.Time
	UserID    string
	SessionID string
	Limit     int
	Offset    int
}

type ReportHistoryItem struct {
	ID                 string          `json:"id"`
	SessionID          string          `json:"session_id"`
	UserID             string          `json:"user_id"`
	Mode               string          `json:"mode"`
	SessionStatus      string          `json:"session_status"`
	TargetPart         *int            `json:"target_part,omitempty"`
	Version            int             `json:"version"`
	ReportStatus       string          `json:"report_status"`
	OverallBand        *float64        `json:"overall_band,omitempty"`
	Confidence         *float64        `json:"confidence,omitempty"`
	Criteria           json.RawMessage `json:"criteria"`
	SessionCreatedAt   time.Time       `json:"session_created_at"`
	SessionCompletedAt *time.Time      `json:"session_completed_at,omitempty"`
	ReportCreatedAt    time.Time       `json:"report_created_at"`
	ReportUpdatedAt    time.Time       `json:"report_updated_at"`
}

type CriterionScore struct {
	ID          string          `json:"id"`
	ReportID    string          `json:"report_id"`
	Criterion   string          `json:"criterion"`
	Band        float64         `json:"band"`
	Confidence  float64         `json:"confidence"`
	Evidence    json.RawMessage `json:"evidence"`
	Suggestions json.RawMessage `json:"suggestions"`
	RawOutput   json.RawMessage `json:"raw_output"`
	CreatedAt   time.Time       `json:"created_at"`
}

type FeedbackItem struct {
	ID           string          `json:"id"`
	ReportID     string          `json:"report_id"`
	Category     string          `json:"category"`
	Priority     int             `json:"priority"`
	Title        string          `json:"title"`
	Body         string          `json:"body"`
	EvidenceRefs json.RawMessage `json:"evidence_refs"`
	CreatedAt    time.Time       `json:"created_at"`
}

type ReferenceAnswer struct {
	ID                   string          `json:"id"`
	ReportID             string          `json:"report_id"`
	TurnID               *string         `json:"turn_id,omitempty"`
	BandTarget           *float64        `json:"band_target,omitempty"`
	Skeleton             json.RawMessage `json:"skeleton"`
	AnswerText           string          `json:"answer_text"`
	PersonalizationNotes *string         `json:"personalization_notes,omitempty"`
	CreatedAt            time.Time       `json:"created_at"`
}

type StudyPlan struct {
	ID        string    `json:"id"`
	ReportID  *string   `json:"report_id,omitempty"`
	UserID    string    `json:"user_id"`
	Priority  int       `json:"priority"`
	Focus     string    `json:"focus"`
	Task      string    `json:"task"`
	DueOn     *string   `json:"due_on,omitempty"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type ReportUserFeedback struct {
	ID         string          `json:"id"`
	ReportID   string          `json:"report_id"`
	SessionID  string          `json:"session_id"`
	UserID     string          `json:"user_id"`
	TargetType string          `json:"target_type"`
	TargetID   *string         `json:"target_id,omitempty"`
	Vote       string          `json:"vote"`
	Comment    *string         `json:"comment,omitempty"`
	Metadata   json.RawMessage `json:"metadata"`
	CreatedAt  time.Time       `json:"created_at"`
}

type ReportFeedbackFilter struct {
	ReportID   string
	SessionID  string
	TargetType string
	Vote       string
	Limit      int
	Offset     int
}

type SaveReportInput struct {
	ReportID         *string                        `json:"report_id"`
	Version          int                            `json:"version" binding:"omitempty,min=1"`
	Status           string                         `json:"status" binding:"omitempty,oneof=generating ready failed"`
	OverallBand      *float64                       `json:"overall_band" binding:"omitempty,min=0,max=9"`
	Confidence       *float64                       `json:"confidence" binding:"omitempty,min=0,max=1"`
	Disclaimer       string                         `json:"disclaimer"`
	ModelRunID       *string                        `json:"model_run_id"`
	Criteria         map[string]CriterionScoreInput `json:"criteria" binding:"required"`
	ReviewerNotes    []string                       `json:"reviewer_notes"`
	NextPracticePlan []StudyPlanInput               `json:"next_practice_plan"`
	FeedbackItems    []FeedbackItemInput            `json:"feedback_items"`
	ReferenceAnswers []ReferenceAnswerInput         `json:"reference_answers"`
	RawReport        map[string]any                 `json:"raw_report"`
}

type SubmitReportFeedbackInput struct {
	TargetType string         `json:"target_type" binding:"required"`
	TargetID   *string        `json:"target_id"`
	Vote       string         `json:"vote" binding:"required"`
	Comment    *string        `json:"comment"`
	Metadata   map[string]any `json:"metadata"`
}

type CriterionScoreInput struct {
	Band        float64          `json:"band" binding:"required,min=0,max=9"`
	Confidence  float64          `json:"confidence" binding:"required,min=0,max=1"`
	Evidence    []map[string]any `json:"evidence"`
	Suggestions []string         `json:"suggestions"`
	RawOutput   map[string]any   `json:"raw_output"`
}

type FeedbackItemInput struct {
	Category     string           `json:"category" binding:"required,min=1,max=120"`
	Priority     int              `json:"priority" binding:"omitempty,min=1,max=5"`
	Title        string           `json:"title" binding:"required,min=1,max=240"`
	Body         string           `json:"body" binding:"required,min=1"`
	EvidenceRefs []map[string]any `json:"evidence_refs"`
}

type ReferenceAnswerInput struct {
	TurnID               *string        `json:"turn_id"`
	BandTarget           *float64       `json:"band_target" binding:"omitempty,min=0,max=9"`
	Skeleton             map[string]any `json:"skeleton"`
	AnswerText           string         `json:"answer_text" binding:"required,min=1"`
	PersonalizationNotes *string        `json:"personalization_notes"`
}

type StudyPlanInput struct {
	Priority int     `json:"priority" binding:"omitempty,min=1,max=5"`
	Focus    string  `json:"focus" binding:"required,min=1,max=160"`
	Task     string  `json:"task" binding:"required,min=1"`
	DueOn    *string `json:"due_on"`
}

func (input *SaveReportInput) Normalize() {
	if input.Version == 0 {
		input.Version = 1
	}
	if input.Status == "" {
		input.Status = StatusReady
	}
	if input.Disclaimer == "" {
		input.Disclaimer = IELTSDisclaimer
	}
	for index := range input.FeedbackItems {
		if input.FeedbackItems[index].Priority == 0 {
			input.FeedbackItems[index].Priority = 3
		}
	}
	for index := range input.NextPracticePlan {
		if input.NextPracticePlan[index].Priority == 0 {
			input.NextPracticePlan[index].Priority = index + 1
			if input.NextPracticePlan[index].Priority > 5 {
				input.NextPracticePlan[index].Priority = 5
			}
		}
	}
}

func (input SaveReportInput) Validate(sessionID string) error {
	if sessionID == "" {
		return fmt.Errorf("%w: session_id is required", ErrInvalidInput)
	}
	if input.Disclaimer != IELTSDisclaimer {
		return fmt.Errorf("%w: disclaimer must match practice disclaimer", ErrInvalidInput)
	}
	if input.Status == StatusReady && (input.OverallBand == nil || input.Confidence == nil) {
		return fmt.Errorf("%w: ready report requires overall_band and confidence", ErrInvalidInput)
	}
	for _, criterion := range requiredCriteria {
		if _, ok := input.Criteria[criterion]; !ok {
			return fmt.Errorf("%w: criteria missing %s", ErrInvalidInput, criterion)
		}
	}
	for criterion, score := range input.Criteria {
		if !isKnownCriterion(criterion) {
			return fmt.Errorf("%w: unknown criterion %s", ErrInvalidInput, criterion)
		}
		if !isHalfBand(score.Band) {
			return fmt.Errorf("%w: criterion band must be in 0.5 increments", ErrInvalidInput)
		}
	}
	if input.OverallBand != nil && !isHalfBand(*input.OverallBand) {
		return fmt.Errorf("%w: overall_band must be in 0.5 increments", ErrInvalidInput)
	}
	for _, item := range input.ReferenceAnswers {
		if item.BandTarget != nil && !isHalfBand(*item.BandTarget) {
			return fmt.Errorf("%w: band_target must be in 0.5 increments", ErrInvalidInput)
		}
	}
	return nil
}

func (input *SubmitReportFeedbackInput) Normalize() {
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.Vote = strings.TrimSpace(input.Vote)
	if input.TargetID != nil {
		trimmed := strings.TrimSpace(*input.TargetID)
		if trimmed == "" {
			input.TargetID = nil
		} else {
			input.TargetID = &trimmed
		}
	}
	if input.Comment != nil {
		trimmed := strings.TrimSpace(*input.Comment)
		if trimmed == "" {
			input.Comment = nil
		} else {
			input.Comment = &trimmed
		}
	}
}

func (input SubmitReportFeedbackInput) Validate() error {
	if input.TargetType == "" {
		return fmt.Errorf("%w: target_type is required", ErrInvalidInput)
	}
	if !isKnownFeedbackTargetType(input.TargetType) {
		return fmt.Errorf("%w: unknown feedback target_type %s", ErrInvalidInput, input.TargetType)
	}
	if input.Vote != "up" && input.Vote != "down" {
		return fmt.Errorf("%w: vote must be up or down", ErrInvalidInput)
	}
	if input.TargetType == "overall" && input.TargetID != nil && *input.TargetID != "" {
		return fmt.Errorf("%w: overall feedback cannot target a child item", ErrInvalidInput)
	}
	if input.TargetType != "overall" && (input.TargetID == nil || *input.TargetID == "") {
		return fmt.Errorf("%w: target_id is required for item-level feedback", ErrInvalidInput)
	}
	if input.TargetType != "overall" && input.TargetID != nil && !uuidPattern.MatchString(*input.TargetID) {
		return fmt.Errorf("%w: target_id must be a uuid", ErrInvalidInput)
	}
	if input.Comment != nil && len(*input.Comment) > 2000 {
		return fmt.Errorf("%w: comment is too long", ErrInvalidInput)
	}
	return nil
}

func isKnownFeedbackTargetType(value string) bool {
	for _, targetType := range feedbackTargetTypes {
		if value == targetType {
			return true
		}
	}
	return false
}

func isKnownCriterion(value string) bool {
	for _, criterion := range requiredCriteria {
		if value == criterion {
			return true
		}
	}
	return false
}

func isHalfBand(value float64) bool {
	return value*2 == float64(int(value*2))
}
