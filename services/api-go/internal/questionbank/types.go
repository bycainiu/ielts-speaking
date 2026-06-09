package questionbank

import (
	"encoding/json"
	"time"
)

const (
	StatusDraft    = "draft"
	StatusActive   = "active"
	StatusArchived = "archived"

	SourceOriginal   = "original"
	SourceAuthorized = "authorized"
	SourceUserRecall = "user_recall"
	SourceInternal   = "internal"
)

type Season struct {
	ID        string     `json:"id"`
	Code      string     `json:"code"`
	Title     string     `json:"title"`
	StartsOn  *string    `json:"starts_on,omitempty"`
	EndsOn    *string    `json:"ends_on,omitempty"`
	Status    string     `json:"status"`
	IsActive  bool       `json:"is_active"`
	CreatedAt time.Time  `json:"created_at"`
	UpdatedAt time.Time  `json:"updated_at"`
	DeletedAt *time.Time `json:"deleted_at,omitempty"`
}

type SeasonInput struct {
	Code     string  `json:"code" binding:"required,min=2,max=40"`
	Title    string  `json:"title" binding:"required,min=2,max=120"`
	StartsOn *string `json:"starts_on" binding:"omitempty,datetime=2006-01-02"`
	EndsOn   *string `json:"ends_on" binding:"omitempty,datetime=2006-01-02"`
	Status   string  `json:"status" binding:"omitempty,oneof=draft active archived reviewing"`
}

type Topic struct {
	ID         string     `json:"id"`
	CategoryID *string    `json:"category_id,omitempty"`
	Name       string     `json:"name"`
	Slug       string     `json:"slug"`
	Status     string     `json:"status"`
	CreatedAt  time.Time  `json:"created_at"`
	UpdatedAt  time.Time  `json:"updated_at"`
	DeletedAt  *time.Time `json:"deleted_at,omitempty"`
}

type TopicInput struct {
	CategoryID *string `json:"category_id"`
	Name       string  `json:"name" binding:"required,min=2,max=120"`
	Slug       string  `json:"slug" binding:"required,min=2,max=120"`
	Status     string  `json:"status" binding:"omitempty,oneof=draft active archived reviewing"`
}

type CueCard struct {
	ID                 string    `json:"id"`
	QuestionID         string    `json:"question_id"`
	Prompt             string    `json:"prompt"`
	BulletPoints       []string  `json:"bullet_points"`
	PreparationSeconds int       `json:"preparation_seconds"`
	SpeakingSeconds    int       `json:"speaking_seconds"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}

type CueCardInput struct {
	Prompt             string   `json:"prompt" binding:"required,min=2,max=2000"`
	BulletPoints       []string `json:"bullet_points" binding:"omitempty,dive,max=240"`
	PreparationSeconds int      `json:"preparation_seconds" binding:"omitempty,min=0,max=120"`
	SpeakingSeconds    int      `json:"speaking_seconds" binding:"omitempty,min=60,max=240"`
}

type FollowupTemplate struct {
	ID           string    `json:"id"`
	QuestionID   *string   `json:"question_id,omitempty"`
	Part         int       `json:"part"`
	Text         string    `json:"text"`
	TriggerHint  *string   `json:"trigger_hint,omitempty"`
	SortOrder    int       `json:"sort_order"`
	ReviewStatus string    `json:"review_status"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

type FollowupTemplateInput struct {
	Part         int     `json:"part" binding:"required,oneof=1 2 3"`
	Text         string  `json:"text" binding:"required,min=2,max=1000"`
	TriggerHint  *string `json:"trigger_hint" binding:"omitempty,max=400"`
	SortOrder    int     `json:"sort_order" binding:"omitempty,min=0,max=1000"`
	ReviewStatus string  `json:"review_status" binding:"omitempty,oneof=draft active archived reviewing"`
}

type Question struct {
	ID           string             `json:"id"`
	SeasonID     *string            `json:"season_id,omitempty"`
	TopicID      *string            `json:"topic_id,omitempty"`
	Part         int                `json:"part"`
	Text         string             `json:"text"`
	Difficulty   *int               `json:"difficulty,omitempty"`
	SourceType   string             `json:"source_type"`
	License      *string            `json:"license,omitempty"`
	ReviewStatus string             `json:"review_status"`
	Metadata     json.RawMessage    `json:"metadata"`
	CueCard      *CueCard           `json:"cue_card,omitempty"`
	Followups    []FollowupTemplate `json:"followup_templates"`
	CreatedBy    *string            `json:"created_by,omitempty"`
	CreatedAt    time.Time          `json:"created_at"`
	UpdatedAt    time.Time          `json:"updated_at"`
	DeletedAt    *time.Time         `json:"deleted_at,omitempty"`
}

type QuestionInput struct {
	SeasonID     *string                 `json:"season_id"`
	TopicID      *string                 `json:"topic_id"`
	Part         int                     `json:"part" binding:"required,oneof=1 2 3"`
	Text         string                  `json:"text" binding:"required,min=2,max=2000"`
	Difficulty   *int                    `json:"difficulty" binding:"omitempty,min=1,max=5"`
	SourceType   string                  `json:"source_type" binding:"omitempty,oneof=original authorized user_recall internal"`
	License      *string                 `json:"license" binding:"omitempty,max=160"`
	ReviewStatus string                  `json:"review_status" binding:"omitempty,oneof=draft active archived reviewing"`
	Metadata     map[string]any          `json:"metadata"`
	CueCard      *CueCardInput           `json:"cue_card"`
	Followups    []FollowupTemplateInput `json:"followup_templates"`
}

type QuestionFilter struct {
	SeasonID     string
	TopicID      string
	Part         *int
	ReviewStatus string
	IncludeDraft bool
	Limit        int
	Offset       int
}

type AdminAuditInput struct {
	ActorUserID string         `json:"actor_user_id"`
	ActorRole   string         `json:"actor_role"`
	Action      string         `json:"action"`
	Resource    string         `json:"resource"`
	Method      string         `json:"method"`
	Path        string         `json:"path"`
	StatusCode  int            `json:"status_code"`
	Metadata    map[string]any `json:"metadata"`
}
