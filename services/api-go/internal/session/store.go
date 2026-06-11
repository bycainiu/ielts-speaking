package session

import "context"

type Store interface {
	CreateSession(ctx context.Context, userID string, input CreateSessionInput) (PracticeSession, error)
	ListSessions(ctx context.Context, userID string, filter SessionFilter) ([]PracticeSession, error)
	GetSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	GetSessionForAdmin(ctx context.Context, sessionID string) (PracticeSession, error)
	GetSessionContextsForAdmin(ctx context.Context, sessionIDs []string) ([]AdminSessionContext, error)
	GetUserContextsByHashForAdmin(ctx context.Context, userHashes []string) ([]AdminUserContext, error)
	StartSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	PauseSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	ResumeSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	UpdateSessionState(ctx context.Context, userID string, sessionID string, input UpdateSessionStateInput) (PracticeSession, error)
	CompletePart(ctx context.Context, userID string, sessionID string, part int) (PracticeSession, error)
	FinishSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	CancelSession(ctx context.Context, userID string, sessionID string) (PracticeSession, error)
	CreateTurn(ctx context.Context, userID string, sessionID string, input CreateTurnInput) (SessionTurn, error)
	UpdateTurn(ctx context.Context, userID string, sessionID string, turnID string, input UpdateTurnInput) (SessionTurn, error)
	AttachAudioAsset(ctx context.Context, userID string, sessionID string, turnID string, input AudioAssetInput) (AudioAsset, error)
	SaveASRResult(ctx context.Context, userID string, sessionID string, turnID string, input ASRResultInput) (ASRResult, error)
	CorrectASRResult(ctx context.Context, userID string, sessionID string, turnID string, asrResultID string, input CorrectASRResultInput) (ASRResult, error)
	SaveSpeechMetrics(ctx context.Context, userID string, sessionID string, turnID string, input SpeechMetricsInput) (SpeechMetrics, error)
}
