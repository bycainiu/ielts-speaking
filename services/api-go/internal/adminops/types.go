package adminops

import "time"

const (
	StatusDraft     = "draft"
	StatusReviewing = "reviewing"
	StatusActive    = "active"
	StatusArchived  = "archived"
)

var allowedStatuses = map[string]struct{}{
	StatusDraft:     {},
	StatusReviewing: {},
	StatusActive:    {},
	StatusArchived:  {},
}

var allowedDocTypes = map[string]struct{}{
	"question_bank":   {},
	"rubric":          {},
	"user_profile":    {},
	"topic_knowledge": {},
	"review_history":  {},
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

type KnowledgeDoc struct {
	ID             string         `json:"id"`
	DocType        string         `json:"doc_type"`
	OwnerUserID    *string        `json:"owner_user_id,omitempty"`
	SourceID       *string        `json:"source_id,omitempty"`
	Title          string         `json:"title"`
	ContentHash    string         `json:"content_hash"`
	Metadata       map[string]any `json:"metadata"`
	Status         string         `json:"status"`
	ChunkCount     int            `json:"chunk_count"`
	TokenCount     int            `json:"token_count"`
	EmbeddingModel *string        `json:"embedding_model,omitempty"`
	CreatedAt      time.Time      `json:"created_at"`
	UpdatedAt      time.Time      `json:"updated_at"`
	DeletedAt      *time.Time     `json:"deleted_at,omitempty"`
}

type KnowledgeDocInput struct {
	DocType  string         `json:"doc_type" binding:"required,oneof=question_bank rubric user_profile topic_knowledge review_history"`
	Title    string         `json:"title" binding:"required,min=2,max=160"`
	Content  string         `json:"content" binding:"required,min=2,max=50000"`
	Status   string         `json:"status" binding:"omitempty,oneof=draft reviewing active archived"`
	Metadata map[string]any `json:"metadata"`
}

type KnowledgeDocUpdateInput struct {
	Title    string         `json:"title" binding:"required,min=2,max=160"`
	Content  *string        `json:"content" binding:"omitempty,min=2,max=50000"`
	Status   string         `json:"status" binding:"omitempty,oneof=draft reviewing active archived"`
	Metadata map[string]any `json:"metadata"`
}

type KnowledgeDocFilter struct {
	DocType string
	Status  string
	Limit   int
	Offset  int
}

type PromptVersion struct {
	ID          string         `json:"id"`
	AgentName   string         `json:"agent_name"`
	Purpose     string         `json:"purpose"`
	Version     string         `json:"version"`
	ContentHash string         `json:"content_hash"`
	Metadata    map[string]any `json:"metadata"`
	Active      bool           `json:"active"`
	CreatedAt   time.Time      `json:"created_at"`
}

type PromptVersionFilter struct {
	AgentName string
	Purpose   string
	Active    *bool
	Limit     int
	Offset    int
}

type ContentReviewSummaryItem struct {
	ContentType string `json:"content_type"`
	Status      string `json:"status"`
	Count       int    `json:"count"`
}

type ReferenceAnswerReview struct {
	ID                   string         `json:"id"`
	ReportID             string         `json:"report_id"`
	TurnID               *string        `json:"turn_id,omitempty"`
	BandTarget           *float64       `json:"band_target,omitempty"`
	Skeleton             map[string]any `json:"skeleton"`
	AnswerText           string         `json:"answer_text"`
	PersonalizationNotes *string        `json:"personalization_notes,omitempty"`
	ReviewStatus         string         `json:"review_status"`
	CreatedAt            time.Time      `json:"created_at"`
}

type ReferenceAnswerFilter struct {
	Status string
	Limit  int
	Offset int
}

type StatusUpdateInput struct {
	Status string `json:"status" binding:"required,oneof=draft reviewing active archived"`
}
