package knowledgeingestion

import (
	"context"
	"io"
	"time"
)

const (
	VisibilityPrivate = "private"
	VisibilityPublic  = "public"

	PurposeAuto         = "auto"
	PurposeQuestionBank = "question_bank"
	PurposeKnowledge    = "knowledge"
	PurposeBackground   = "background"
	PurposeMixed        = "mixed"

	JobStatusQueued                 = "queued"
	JobStatusRunning                = "running"
	JobStatusAwaitingReview         = "awaiting_review"
	JobStatusAwaitingUserConfirm    = "awaiting_user_confirmation"
	JobStatusCompleted              = "completed"
	JobStatusFailed                 = "failed"
	JobStatusCancelled              = "cancelled"
	JobStatusRejected               = "rejected"
	CandidateKindQuestion           = "question"
	CandidateKindKnowledge          = "knowledge"
	CandidateKindBackground         = "background"
	CandidateStatusPending          = "pending"
	CandidateStatusApproved         = "approved"
	CandidateStatusRejected         = "rejected"
	CandidateStatusConfirmed        = "confirmed"
	CandidateStatusMaterialized     = "materialized"
	ReviewDecisionApprove           = "approve"
	ReviewDecisionReject            = "reject"
	ReviewDecisionConfirm           = "confirm"
	ReviewDecisionRetry             = "retry"
	ReviewDecisionCancel            = "cancel"
	ArtifactKindOriginal            = "original"
	ArtifactKindExtractedText       = "extracted_text"
	ArtifactKindNormalizedText      = "normalized_text"
	ArtifactKindCommandOutput       = "command_output"
	ArtifactKindPreview             = "preview"
	ArtifactKindCandidateExport     = "candidate_export"
	ArtifactKindMaterializeSimulate = "materialization_simulation"
)

type Store interface {
	CreateUpload(ctx context.Context, input CreateUploadRecordInput) (KnowledgeImportJobDetail, error)
	ListUserJobs(ctx context.Context, userID string, filter UserJobFilter) ([]KnowledgeImportJobSummary, error)
	ListAdminJobs(ctx context.Context, filter AdminJobFilter) ([]KnowledgeImportJobSummary, error)
	GetJobDetail(ctx context.Context, jobID string) (KnowledgeImportJobDetail, error)
	ConfirmBackgroundCandidates(ctx context.Context, userID string, jobID string, input ConfirmBackgroundInput) (KnowledgeImportJobDetail, error)
	ReviewJob(ctx context.Context, reviewerUserID string, reviewerRole string, jobID string, input AdminReviewInput) (KnowledgeImportJobDetail, error)
	CancelJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error)
	RetryJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error)
	GetRuntimePolicy(ctx context.Context) (RuntimePolicy, error)
	UpdateRuntimePolicy(ctx context.Context, actorUserID string, input RuntimePolicyUpdateInput) (RuntimePolicy, error)
	GetArtifact(ctx context.Context, artifactID string) (KnowledgeIngestionArtifact, error)
}

type Service struct {
	store    Store
	objects  ObjectStore
	bucket   string
	maxBytes int64
}

type ObjectStore interface {
	EnsureBucket(ctx context.Context, bucket string) error
	PutObject(ctx context.Context, bucket string, key string, content io.Reader, size int64, contentType string) error
	PresignedGetObject(ctx context.Context, bucket string, key string, expires time.Duration, publicHostname string) (string, error)
}

type ReadSeekCloser interface {
	io.Reader
	io.Seeker
}

type CreateUploadInput struct {
	UserID     string
	Visibility string
	Purpose    string
	Title      string
	FileName   string
	MimeType   string
	SizeBytes  int64
	Content    ReadSeekCloser
}

type CreateUploadRecordInput struct {
	OwnerUserID     string
	Visibility      string
	Purpose         string
	Title           string
	OriginalFile    string
	Extension       string
	MimeType        string
	SizeBytes       int64
	ChecksumSHA256  string
	StorageBucket   string
	StorageKey      string
	SourceMetadata  map[string]any
	RequestedAction string
}

type UserJobFilter struct {
	Status string
	Limit  int
	Offset int
}

type AdminJobFilter struct {
	Status     string
	Visibility string
	OwnerUserID string
	Limit      int
	Offset     int
}

type ConfirmBackgroundInput struct {
	CandidateIDs      []string `json:"candidate_ids"`
	OverwriteExisting bool     `json:"overwrite_existing"`
}

type AdminReviewInput struct {
	Decision     string   `json:"decision" binding:"required,oneof=approve reject"`
	CandidateIDs []string `json:"candidate_ids"`
	Notes        string   `json:"notes"`
}

type RuntimePolicyUpdateInput struct {
	MaxConcurrency int  `json:"max_concurrency" binding:"required,min=1,max=16"`
	Paused         bool `json:"paused"`
}

type RuntimePolicy struct {
	PolicyKey      string         `json:"policy_key"`
	MaxConcurrency int            `json:"max_concurrency"`
	Paused         bool           `json:"paused"`
	Raw            map[string]any `json:"raw"`
	UpdatedBy      *string        `json:"updated_by,omitempty"`
	UpdatedAt      time.Time      `json:"updated_at"`
}

type KnowledgeSourceFile struct {
	ID               string         `json:"id"`
	OwnerUserID      string         `json:"owner_user_id"`
	Visibility       string         `json:"visibility"`
	UploadPurpose    string         `json:"upload_purpose"`
	Title            string         `json:"title"`
	OriginalFilename string         `json:"original_filename"`
	Extension        string         `json:"extension"`
	MimeType         string         `json:"mime_type"`
	SizeBytes        int64          `json:"size_bytes"`
	ChecksumSHA256   string         `json:"checksum_sha256"`
	StorageBucket    string         `json:"storage_bucket"`
	StorageKey       string         `json:"storage_key"`
	Metadata         map[string]any `json:"metadata"`
	CreatedAt        time.Time      `json:"created_at"`
}

type KnowledgeImportJobSummary struct {
	ID                   string         `json:"id"`
	OwnerUserID          string         `json:"owner_user_id"`
	RequestedVisibility  string         `json:"requested_visibility"`
	RequestedAction      string         `json:"requested_action"`
	Status               string         `json:"status"`
	Stage                string         `json:"stage"`
	Priority             int            `json:"priority"`
	ProgressPct          int            `json:"progress_pct"`
	ClassifierLabel      *string        `json:"classifier_label,omitempty"`
	ClassifierConfidence *float64       `json:"classifier_confidence,omitempty"`
	RunID                *string        `json:"run_id,omitempty"`
	ErrorCode            *string        `json:"error_code,omitempty"`
	ErrorMessage         *string        `json:"error_message,omitempty"`
	DuplicateOfJobID     *string        `json:"duplicate_of_job_id,omitempty"`
	QueuedAt             time.Time      `json:"queued_at"`
	StartedAt            *time.Time     `json:"started_at,omitempty"`
	HeartbeatAt          *time.Time     `json:"heartbeat_at,omitempty"`
	FinishedAt           *time.Time     `json:"finished_at,omitempty"`
	MaterializedAt       *time.Time     `json:"materialized_at,omitempty"`
	UpdatedAt            time.Time      `json:"updated_at"`
	Metadata             map[string]any `json:"metadata"`
	SourceFile           KnowledgeSourceFile `json:"source_file"`
	CandidateCounts      map[string]int `json:"candidate_counts"`
}

type KnowledgeIngestionCandidate struct {
	ID                  string         `json:"id"`
	JobID               string         `json:"job_id"`
	CandidateKind       string         `json:"candidate_kind"`
	Title               string         `json:"title"`
	Summary             *string        `json:"summary,omitempty"`
	Content             string         `json:"content"`
	CandidateStatus     string         `json:"candidate_status"`
	NormalizedPayload   map[string]any `json:"normalized_payload"`
	MaterializationPlan map[string]any `json:"materialization_plan"`
	Metadata            map[string]any `json:"metadata"`
	CreatedAt           time.Time      `json:"created_at"`
	UpdatedAt           time.Time      `json:"updated_at"`
}

type KnowledgeIngestionReview struct {
	ID             string         `json:"id"`
	JobID          string         `json:"job_id"`
	CandidateID    *string        `json:"candidate_id,omitempty"`
	ReviewerUserID string         `json:"reviewer_user_id"`
	ReviewerRole   string         `json:"reviewer_role"`
	Decision       string         `json:"decision"`
	Notes          *string        `json:"notes,omitempty"`
	Payload        map[string]any `json:"payload"`
	CreatedAt      time.Time      `json:"created_at"`
}

type KnowledgeIngestionArtifact struct {
	ID           string         `json:"id"`
	JobID        string         `json:"job_id"`
	RunID        *string        `json:"run_id,omitempty"`
	ArtifactKind string         `json:"artifact_kind"`
	Title        string         `json:"title"`
	ContentType  string         `json:"content_type"`
	StorageBucket *string       `json:"storage_bucket,omitempty"`
	StorageKey   *string        `json:"storage_key,omitempty"`
	SizeBytes    *int64         `json:"size_bytes,omitempty"`
	InlineText   *string        `json:"inline_text,omitempty"`
	Metadata     map[string]any `json:"metadata"`
	CreatedAt    time.Time      `json:"created_at"`
}

type AgentRunStep struct {
	ID                string         `json:"id"`
	WorkflowNode      string         `json:"workflow_node"`
	AgentName         *string        `json:"agent_name,omitempty"`
	PromptVersion     *string        `json:"prompt_version,omitempty"`
	ModelName         *string        `json:"model_name,omitempty"`
	ExecutionKind     *string        `json:"execution_kind,omitempty"`
	Status            string         `json:"status"`
	InputSummary      *string        `json:"input_summary,omitempty"`
	OutputSummary     *string        `json:"output_summary,omitempty"`
	InputPayload      any            `json:"input_payload,omitempty"`
	InputDetail       any            `json:"input_detail,omitempty"`
	OutputPayload     any            `json:"output_payload,omitempty"`
	Messages          any            `json:"messages,omitempty"`
	RetrievedChunks   any            `json:"retrieved_chunks,omitempty"`
	StructuredOutputValidity *bool   `json:"structured_output_validity,omitempty"`
	ScoringResult     any            `json:"scoring_result,omitempty"`
	Part              *int           `json:"part,omitempty"`
	QuestionID        *string        `json:"question_id,omitempty"`
	InputTokens       *int           `json:"input_tokens,omitempty"`
	OutputTokens      *int           `json:"output_tokens,omitempty"`
	EstimatedCostUSD  *float64       `json:"estimated_cost_usd,omitempty"`
	LatencyMS         *int           `json:"latency_ms,omitempty"`
	ErrorCode         *string        `json:"error_code,omitempty"`
	ErrorType         *string        `json:"error_type,omitempty"`
	StartedAt         time.Time      `json:"started_at"`
	FinishedAt        *time.Time     `json:"finished_at,omitempty"`
}

type AgentModelCall struct {
	ID            string     `json:"id"`
	StepID        *string    `json:"step_id,omitempty"`
	CallName      *string    `json:"call_name,omitempty"`
	AgentName     *string    `json:"agent_name,omitempty"`
	ExecutionKind *string    `json:"execution_kind,omitempty"`
	PayloadOrigin *string    `json:"payload_origin,omitempty"`
	PromptVersion *string    `json:"prompt_version,omitempty"`
	Purpose       string     `json:"purpose"`
	ModelName     string     `json:"model_name"`
	Status        string     `json:"status"`
	LatencyMS     *int       `json:"latency_ms,omitempty"`
	InputTokens   *int       `json:"input_tokens,omitempty"`
	OutputTokens  *int       `json:"output_tokens,omitempty"`
	ErrorCode     *string    `json:"error_code,omitempty"`
	OutputSummary *string    `json:"output_summary,omitempty"`
	RequestPayload any       `json:"request_payload,omitempty"`
	ResponsePayload any      `json:"response_payload,omitempty"`
	CreatedAt     time.Time  `json:"created_at"`
}

type AgentRunEvent struct {
	ID         string         `json:"id"`
	StepID     *string        `json:"step_id,omitempty"`
	EventIndex int            `json:"event_index"`
	EventType  string         `json:"event_type"`
	Title      *string        `json:"title,omitempty"`
	Summary    *string        `json:"summary,omitempty"`
	Visibility string         `json:"visibility"`
	Payload    map[string]any `json:"payload"`
	CreatedAt  time.Time      `json:"created_at"`
}

type AgentRunArtifact struct {
	ID           string         `json:"id"`
	StepID       *string        `json:"step_id,omitempty"`
	ArtifactKind string         `json:"artifact_kind"`
	Title        string         `json:"title"`
	ContentType  string         `json:"content_type"`
	StorageBucket *string       `json:"storage_bucket,omitempty"`
	StorageKey   *string        `json:"storage_key,omitempty"`
	SizeBytes    *int64         `json:"size_bytes,omitempty"`
	InlineText   *string        `json:"inline_text,omitempty"`
	Metadata     map[string]any `json:"metadata"`
	CreatedAt    time.Time      `json:"created_at"`
}

type KnowledgeImportRunDetail struct {
	RunID       string             `json:"run_id"`
	RunKind     string             `json:"run_kind"`
	SubjectType *string            `json:"subject_type,omitempty"`
	SubjectID   *string            `json:"subject_id,omitempty"`
	Status      string             `json:"status"`
	StartedAt   time.Time          `json:"started_at"`
	FinishedAt  *time.Time         `json:"finished_at,omitempty"`
	Steps       []AgentRunStep     `json:"steps"`
	ModelCalls  []AgentModelCall   `json:"model_calls"`
	Events      []AgentRunEvent    `json:"events"`
	Artifacts   []AgentRunArtifact `json:"artifacts"`
}

type KnowledgeImportJobDetail struct {
	KnowledgeImportJobSummary
	Candidates []KnowledgeIngestionCandidate `json:"candidates"`
	Reviews    []KnowledgeIngestionReview    `json:"reviews"`
	Artifacts  []KnowledgeIngestionArtifact  `json:"artifacts"`
	Run        *KnowledgeImportRunDetail     `json:"run,omitempty"`
}

type ArtifactPreview struct {
	Artifact  KnowledgeIngestionArtifact `json:"artifact"`
	SignedURL *string                    `json:"signed_url,omitempty"`
}
