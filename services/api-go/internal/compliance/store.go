package compliance

import "context"

type Store interface {
	SaveConsent(ctx context.Context, userID string, input SaveConsentInput) (ConsentRecord, error)
	ListConsents(ctx context.Context, userID string, consentType string) ([]ConsentRecord, error)
	DeleteUserData(ctx context.Context, userID string, input DataDeletionInput) (DataDeletionResult, error)
	GetVoiceClonePolicy(ctx context.Context) (VoiceClonePolicy, error)
	UpdateVoiceClonePolicy(ctx context.Context, actorUserID string, input UpdateVoiceClonePolicyInput) (VoiceClonePolicy, error)
}
