package compliance

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

const (
	ConsentTypeRecording     = "recording"
	RecordingConsentVersion  = "recording_consent.v1"
	DataDeletionConfirmation = "DELETE_MY_DATA"
	VoiceClonePolicyKey      = "voice_clone_policy"
	VoiceClonePolicyVersion  = "voice_clone_policy.v1"
)

var (
	ErrInvalidInput = fmt.Errorf("invalid compliance input")
	ErrNotFound     = fmt.Errorf("compliance resource not found")
)

type ConsentRecord struct {
	ID          string          `json:"id"`
	UserID      string          `json:"user_id"`
	ConsentType string          `json:"consent_type"`
	Version     string          `json:"version"`
	Accepted    bool            `json:"accepted"`
	AcceptedAt  *time.Time      `json:"accepted_at,omitempty"`
	Metadata    json.RawMessage `json:"metadata"`
	CreatedAt   time.Time       `json:"created_at"`
}

type SaveConsentInput struct {
	ConsentType string         `json:"consent_type" binding:"required"`
	Version     string         `json:"version"`
	Accepted    bool           `json:"accepted"`
	Metadata    map[string]any `json:"metadata"`
}

type DataDeletionInput struct {
	SessionID        *string `json:"session_id"`
	DeleteRecordings bool    `json:"delete_recordings"`
	DeleteReports    bool    `json:"delete_reports"`
	DeleteBackground bool    `json:"delete_background"`
	Confirmation     string  `json:"confirmation" binding:"required"`
}

type DataDeletionResult struct {
	SessionsDeleted        int `json:"sessions_deleted"`
	AudioAssetsDeleted     int `json:"audio_assets_deleted"`
	BackgroundItemsDeleted int `json:"background_items_deleted"`
}

type VoiceClonePolicy struct {
	Enabled                 bool      `json:"enabled"`
	Version                 string    `json:"version"`
	RequiresExplicitConsent bool      `json:"requires_explicit_consent"`
	UpdatedBy               *string   `json:"updated_by,omitempty"`
	UpdatedAt               time.Time `json:"updated_at"`
}

type UpdateVoiceClonePolicyInput struct {
	Enabled                 bool   `json:"enabled"`
	RequiresExplicitConsent *bool  `json:"requires_explicit_consent"`
	Version                 string `json:"version"`
}

func (input *SaveConsentInput) Normalize() {
	input.ConsentType = strings.TrimSpace(input.ConsentType)
	input.Version = strings.TrimSpace(input.Version)
	if input.Version == "" && input.ConsentType == ConsentTypeRecording {
		input.Version = RecordingConsentVersion
	}
}

func (input SaveConsentInput) Validate() error {
	if input.ConsentType != ConsentTypeRecording {
		return fmt.Errorf("%w: unsupported consent_type", ErrInvalidInput)
	}
	if input.Version == "" {
		return fmt.Errorf("%w: version is required", ErrInvalidInput)
	}
	return nil
}

func (input *DataDeletionInput) Normalize() {
	if input.SessionID != nil {
		trimmed := strings.TrimSpace(*input.SessionID)
		if trimmed == "" {
			input.SessionID = nil
		} else {
			input.SessionID = &trimmed
		}
	}
	input.Confirmation = strings.TrimSpace(input.Confirmation)
}

func (input DataDeletionInput) Validate() error {
	if input.Confirmation != DataDeletionConfirmation {
		return fmt.Errorf("%w: confirmation phrase is required", ErrInvalidInput)
	}
	if !input.DeleteRecordings && !input.DeleteReports && !input.DeleteBackground {
		return fmt.Errorf("%w: at least one deletion target is required", ErrInvalidInput)
	}
	return nil
}

func (input *UpdateVoiceClonePolicyInput) Normalize() {
	input.Version = strings.TrimSpace(input.Version)
	if input.Version == "" {
		input.Version = VoiceClonePolicyVersion
	}
}

func (input UpdateVoiceClonePolicyInput) Validate() error {
	if input.Version == "" {
		return fmt.Errorf("%w: version is required", ErrInvalidInput)
	}
	return nil
}
