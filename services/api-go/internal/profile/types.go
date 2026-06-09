package profile

import (
	"encoding/json"
	"time"
)

const (
	DefaultTimezone = "Asia/Shanghai"

	PrivacyNormal    = "normal"
	PrivacySensitive = "sensitive"
	PrivacyPrivate   = "private"

	UsageQuestionPersonalization = "question_personalization"
	UsageFeedbackPersonalization = "feedback_personalization"
	UsageScoringContext          = "scoring_context"
)

type UserProfile struct {
	ID                string     `json:"id"`
	UserID            string     `json:"user_id"`
	DisplayName       *string    `json:"display_name,omitempty"`
	Timezone          string     `json:"timezone"`
	TargetBand        *float64   `json:"target_band,omitempty"`
	CurrentBand       *float64   `json:"current_band,omitempty"`
	PreferredExamDate *string    `json:"preferred_exam_date,omitempty"`
	CreatedAt         time.Time  `json:"created_at"`
	UpdatedAt         time.Time  `json:"updated_at"`
	DeletedAt         *time.Time `json:"deleted_at,omitempty"`
}

type Questionnaire struct {
	ID                string          `json:"id"`
	UserID            string          `json:"user_id"`
	Version           int             `json:"version"`
	Answers           json.RawMessage `json:"answers"`
	PrivacyExclusions []string        `json:"privacy_exclusions"`
	SubmittedAt       *time.Time      `json:"submitted_at,omitempty"`
	CreatedAt         time.Time       `json:"created_at"`
	UpdatedAt         time.Time       `json:"updated_at"`
}

type BackgroundFact struct {
	ID              string    `json:"id"`
	UserID          string    `json:"user_id"`
	QuestionnaireID *string   `json:"questionnaire_id,omitempty"`
	Topic           *string   `json:"topic,omitempty"`
	FactKey         string    `json:"fact_key"`
	FactValue       string    `json:"fact_value"`
	PrivacyLevel    string    `json:"privacy_level"`
	AllowedUsage    []string  `json:"allowed_usage"`
	IsExcluded      bool      `json:"is_excluded"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

type Background struct {
	Profile       UserProfile      `json:"profile"`
	Questionnaire *Questionnaire   `json:"questionnaire,omitempty"`
	Facts         []BackgroundFact `json:"facts"`
	AgentFacts    []BackgroundFact `json:"agent_facts"`
}

type ProfileInput struct {
	DisplayName       *string  `json:"display_name" binding:"omitempty,max=80"`
	Timezone          string   `json:"timezone" binding:"omitempty,min=1,max=80"`
	TargetBand        *float64 `json:"target_band" binding:"omitempty,min=0,max=9"`
	CurrentBand       *float64 `json:"current_band" binding:"omitempty,min=0,max=9"`
	PreferredExamDate *string  `json:"preferred_exam_date" binding:"omitempty,datetime=2006-01-02"`
}

type BackgroundInput struct {
	Profile           *ProfileInput  `json:"profile"`
	Version           int            `json:"version" binding:"omitempty,min=1,max=100"`
	Answers           map[string]any `json:"answers"`
	PrivacyExclusions []string       `json:"privacy_exclusions" binding:"omitempty,max=100,dive,min=1,max=160"`
	Facts             []FactInput    `json:"facts" binding:"omitempty,max=100,dive"`
	Submitted         bool           `json:"submitted"`
}

type FactInput struct {
	Topic        *string  `json:"topic" binding:"omitempty,max=120"`
	FactKey      string   `json:"fact_key" binding:"required,min=1,max=160"`
	FactValue    string   `json:"fact_value" binding:"required,min=1,max=1000"`
	PrivacyLevel string   `json:"privacy_level" binding:"omitempty,oneof=normal sensitive private"`
	AllowedUsage []string `json:"allowed_usage" binding:"omitempty,max=10,dive,oneof=question_personalization feedback_personalization scoring_context"`
	IsExcluded   bool     `json:"is_excluded"`
}
