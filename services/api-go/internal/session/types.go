package session

import (
	"encoding/json"
	"time"
)

const (
	ModeFullExam      = "full_exam"
	ModePartPractice  = "part_practice"
	ModeTopicPractice = "topic_practice"

	StatusCreated    = "created"
	StatusPlanned    = "planned"
	StatusInProgress = "in_progress"
	StatusPaused     = "paused"
	StatusScoring    = "scoring"
	StatusCompleted  = "completed"
	StatusCancelled  = "cancelled"
	StatusFailed     = "failed"

	TurnStatusPending       = "pending"
	TurnStatusRecording     = "recording"
	TurnStatusASRProcessing = "asr_processing"
	TurnStatusCompleted     = "completed"
	TurnStatusFailed        = "failed"

	SpeakerExaminer = "examiner"
	SpeakerUser     = "user"
)

type PracticeSession struct {
	ID          string          `json:"id"`
	UserID      string          `json:"user_id"`
	Mode        string          `json:"mode"`
	Status      string          `json:"status"`
	SeasonID    *string         `json:"season_id,omitempty"`
	TopicID     *string         `json:"topic_id,omitempty"`
	TargetPart  *int            `json:"target_part,omitempty"`
	State       json.RawMessage `json:"state"`
	StartedAt   *time.Time      `json:"started_at,omitempty"`
	CompletedAt *time.Time      `json:"completed_at,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
	Parts       []SessionPart   `json:"parts"`
	Turns       []SessionTurn   `json:"turns"`
}

type AdminSessionContext struct {
	SessionID       string     `json:"session_id"`
	UserID          string     `json:"user_id"`
	UserEmail       string     `json:"user_email"`
	UserDisplayName *string    `json:"user_display_name,omitempty"`
	Mode            string     `json:"mode"`
	Status          string     `json:"status"`
	SeasonID        *string    `json:"season_id,omitempty"`
	SeasonTitle     *string    `json:"season_title,omitempty"`
	TopicID         *string    `json:"topic_id,omitempty"`
	TopicName       *string    `json:"topic_name,omitempty"`
	TopicLabel      *string    `json:"topic_label,omitempty"`
	PrimaryTopic    *string    `json:"primary_topic,omitempty"`
	SetupSurface    *string    `json:"setup_surface,omitempty"`
	TargetPart      *int       `json:"target_part,omitempty"`
	StartedAt       *time.Time `json:"started_at,omitempty"`
	CompletedAt     *time.Time `json:"completed_at,omitempty"`
	CreatedAt       time.Time  `json:"created_at"`
	UpdatedAt       time.Time  `json:"updated_at"`
}

type AdminUserContext struct {
	UserID          string    `json:"user_id"`
	UserHash        string    `json:"user_hash"`
	UserEmail       string    `json:"user_email"`
	UserDisplayName *string   `json:"user_display_name,omitempty"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

type SessionPart struct {
	ID          string     `json:"id"`
	SessionID   string     `json:"session_id"`
	Part        int        `json:"part"`
	Status      string     `json:"status"`
	OrderIndex  int        `json:"order_index"`
	StartedAt   *time.Time `json:"started_at,omitempty"`
	CompletedAt *time.Time `json:"completed_at,omitempty"`
	CreatedAt   time.Time  `json:"created_at"`
	UpdatedAt   time.Time  `json:"updated_at"`
}

type SessionTurn struct {
	ID           string          `json:"id"`
	SessionID    string          `json:"session_id"`
	PartID       *string         `json:"part_id,omitempty"`
	QuestionID   *string         `json:"question_id,omitempty"`
	TurnIndex    int             `json:"turn_index"`
	Speaker      string          `json:"speaker"`
	Status       string          `json:"status"`
	QuestionText *string         `json:"question_text,omitempty"`
	AnswerText   *string         `json:"answer_text,omitempty"`
	AgentRunID   *string         `json:"agent_run_id,omitempty"`
	Metadata     json.RawMessage `json:"metadata"`
	CreatedAt    time.Time       `json:"created_at"`
	UpdatedAt    time.Time       `json:"updated_at"`
	AudioAssets  []AudioAsset    `json:"audio_assets"`
	ASRResults   []ASRResult     `json:"asr_results"`
	Metrics      []SpeechMetrics `json:"speech_metrics"`
}

type AudioAsset struct {
	ID             string    `json:"id"`
	UserID         *string   `json:"user_id,omitempty"`
	SessionID      *string   `json:"session_id,omitempty"`
	TurnID         *string   `json:"turn_id,omitempty"`
	Kind           string    `json:"kind"`
	StorageBucket  string    `json:"storage_bucket"`
	StorageKey     string    `json:"storage_key"`
	MimeType       string    `json:"mime_type"`
	SizeBytes      int64     `json:"size_bytes"`
	DurationMS     *int      `json:"duration_ms,omitempty"`
	ChecksumSHA256 *string   `json:"checksum_sha256,omitempty"`
	CreatedAt      time.Time `json:"created_at"`
}

type ASRResult struct {
	ID                  string          `json:"id"`
	TurnID              string          `json:"turn_id"`
	AudioAssetID        *string         `json:"audio_asset_id,omitempty"`
	Provider            string          `json:"provider"`
	Model               string          `json:"model"`
	Transcript          string          `json:"transcript"`
	CorrectedTranscript *string         `json:"corrected_transcript,omitempty"`
	CorrectedByUserID   *string         `json:"corrected_by_user_id,omitempty"`
	CorrectedAt         *time.Time      `json:"corrected_at,omitempty"`
	Confidence          *float64        `json:"confidence,omitempty"`
	Segments            json.RawMessage `json:"segments"`
	RawResponseRedacted json.RawMessage `json:"raw_response_redacted"`
	CreatedAt           time.Time       `json:"created_at"`
}

type SpeechMetrics struct {
	ID             string          `json:"id"`
	TurnID         string          `json:"turn_id"`
	AudioAssetID   *string         `json:"audio_asset_id,omitempty"`
	DurationMS     *int            `json:"duration_ms,omitempty"`
	WordsCount     *int            `json:"words_count,omitempty"`
	WPM            *float64        `json:"wpm,omitempty"`
	LongPauseCount *int            `json:"long_pause_count,omitempty"`
	MeanPauseMS    *float64        `json:"mean_pause_ms,omitempty"`
	TotalPauseMS   *int            `json:"total_pause_ms,omitempty"`
	FillerCount    *int            `json:"filler_count,omitempty"`
	FillerRatio    *float64        `json:"filler_ratio,omitempty"`
	ASRConfidence  *float64        `json:"asr_confidence,omitempty"`
	RawMetrics     json.RawMessage `json:"raw_metrics"`
	CreatedAt      time.Time       `json:"created_at"`
}

type CreateSessionInput struct {
	Mode       string         `json:"mode" binding:"required,oneof=full_exam part_practice topic_practice"`
	SeasonID   *string        `json:"season_id"`
	TopicID    *string        `json:"topic_id"`
	TargetPart *int           `json:"target_part" binding:"omitempty,min=1,max=3"`
	State      map[string]any `json:"state"`
}

type UpdateSessionStateInput struct {
	State map[string]any `json:"state" binding:"required"`
}

type SessionFilter struct {
	Mode   string
	Status string
	Limit  int
	Offset int
}

type CreateTurnInput struct {
	Part         int            `json:"part" binding:"required,oneof=1 2 3"`
	QuestionID   *string        `json:"question_id"`
	Speaker      string         `json:"speaker" binding:"required,oneof=examiner user"`
	Status       string         `json:"status" binding:"omitempty,oneof=pending recording asr_processing completed failed"`
	QuestionText *string        `json:"question_text"`
	AnswerText   *string        `json:"answer_text"`
	AgentRunID   *string        `json:"agent_run_id"`
	Metadata     map[string]any `json:"metadata"`
}

type UpdateTurnInput struct {
	Status       *string        `json:"status" binding:"omitempty,oneof=pending recording asr_processing completed failed"`
	QuestionText *string        `json:"question_text"`
	AnswerText   *string        `json:"answer_text"`
	AgentRunID   *string        `json:"agent_run_id"`
	Metadata     map[string]any `json:"metadata"`
}

type AudioAssetInput struct {
	Kind           string  `json:"kind" binding:"required,oneof=user_recording examiner_tts reference"`
	StorageBucket  string  `json:"storage_bucket" binding:"required,min=1,max=160"`
	StorageKey     string  `json:"storage_key" binding:"required,min=1,max=600"`
	MimeType       string  `json:"mime_type" binding:"required,max=120"`
	SizeBytes      int64   `json:"size_bytes" binding:"required,min=0"`
	DurationMS     *int    `json:"duration_ms" binding:"omitempty,min=0"`
	ChecksumSHA256 *string `json:"checksum_sha256" binding:"omitempty,len=64"`
}

type ASRResultInput struct {
	AudioAssetID *string          `json:"audio_asset_id"`
	Provider     string           `json:"provider" binding:"required,max=80"`
	Model        string           `json:"model" binding:"required,max=120"`
	Transcript   string           `json:"transcript"`
	Confidence   *float64         `json:"confidence" binding:"omitempty,min=0,max=1"`
	Segments     []map[string]any `json:"segments"`
	RawResponse  map[string]any   `json:"raw_response"`
}

type CorrectASRResultInput struct {
	CorrectedTranscript string `json:"corrected_transcript" binding:"required,min=1"`
}

type SpeechMetricsInput struct {
	AudioAssetID         *string        `json:"audio_asset_id"`
	Transcript           string         `json:"transcript"`
	DurationMS           *int           `json:"duration_ms" binding:"omitempty,min=1"`
	WordsCount           *int           `json:"words_count" binding:"omitempty,min=0"`
	WPM                  *float64       `json:"wpm" binding:"omitempty,min=0"`
	PauseSegments        []PauseSegment `json:"pause_segments"`
	LongPauseThresholdMS *int           `json:"long_pause_threshold_ms" binding:"omitempty,min=1"`
	LongPauseCount       *int           `json:"long_pause_count" binding:"omitempty,min=0"`
	MeanPauseMS          *float64       `json:"mean_pause_ms" binding:"omitempty,min=0"`
	TotalPauseMS         *int           `json:"total_pause_ms" binding:"omitempty,min=0"`
	FillerCount          *int           `json:"filler_count" binding:"omitempty,min=0"`
	FillerRatio          *float64       `json:"filler_ratio" binding:"omitempty,min=0,max=1"`
	ASRConfidence        *float64       `json:"asr_confidence" binding:"omitempty,min=0,max=1"`
	RawMetrics           map[string]any `json:"raw_metrics"`
}

type PauseSegment struct {
	StartMS int `json:"start_ms" binding:"min=0"`
	EndMS   int `json:"end_ms" binding:"min=0"`
}
