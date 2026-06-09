package realtime

import (
	"encoding/json"
	"time"
)

const (
	EventSessionStarted         = "session.started"
	EventPartStarted            = "part.started"
	EventExaminerThinking       = "examiner.thinking"
	EventExaminerMessage        = "examiner.message"
	EventExaminerAudioReady     = "examiner.audio_ready"
	EventTimerStarted           = "timer.started"
	EventTimerTick              = "timer.tick"
	EventTimerWarning           = "timer.warning"
	EventUserRecordingStarted   = "user.recording_started"
	EventUserSilenceDetected    = "user.silence_detected"
	EventUserAnswerCommitted    = "user.answer_committed"
	EventASRProcessing          = "asr.processing"
	EventASRFinal               = "asr.final"
	EventAgentFollowupPlanned   = "agent.followup_planned"
	EventPartCompleted          = "part.completed"
	EventScoringStarted         = "scoring.started"
	EventScoringDimensionDone   = "scoring.dimension_completed"
	EventScoringReviewCompleted = "scoring.review_completed"
	EventReportReady            = "report.ready"
	EventSessionCompleted       = "session.completed"
	EventErrorRecoverable       = "error.recoverable"
	EventErrorFatal             = "error.fatal"
)

type SessionEvent struct {
	Type      string          `json:"type"`
	SessionID string          `json:"session_id"`
	RunID     string          `json:"run_id"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt string          `json:"created_at"`
}

func (e SessionEvent) Validate(expectedSessionID string) error {
	if !allowedEventTypes[e.Type] {
		return ErrInvalidEvent
	}
	if e.SessionID == "" || e.SessionID != expectedSessionID {
		return ErrInvalidEvent
	}
	if e.RunID == "" {
		return ErrInvalidEvent
	}
	if len(e.Payload) == 0 || !json.Valid(e.Payload) {
		return ErrInvalidEvent
	}
	if _, err := time.Parse(time.RFC3339Nano, e.CreatedAt); err != nil {
		return ErrInvalidEvent
	}
	return nil
}

var allowedEventTypes = map[string]bool{
	EventSessionStarted:         true,
	EventPartStarted:            true,
	EventExaminerThinking:       true,
	EventExaminerMessage:        true,
	EventExaminerAudioReady:     true,
	EventTimerStarted:           true,
	EventTimerTick:              true,
	EventTimerWarning:           true,
	EventUserRecordingStarted:   true,
	EventUserSilenceDetected:    true,
	EventUserAnswerCommitted:    true,
	EventASRProcessing:          true,
	EventASRFinal:               true,
	EventAgentFollowupPlanned:   true,
	EventPartCompleted:          true,
	EventScoringStarted:         true,
	EventScoringDimensionDone:   true,
	EventScoringReviewCompleted: true,
	EventReportReady:            true,
	EventSessionCompleted:       true,
	EventErrorRecoverable:       true,
	EventErrorFatal:             true,
}
