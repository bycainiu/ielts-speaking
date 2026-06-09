package audio

import (
	"context"
	"time"
)

type Store interface {
	EnsureTurnForUser(ctx context.Context, userID string, sessionID string, turnID string) error
	HasAcceptedConsent(ctx context.Context, userID string, consentType string) (bool, error)
	VoiceCloneEnabled(ctx context.Context) (bool, error)
	CreateAsset(ctx context.Context, input CreateAssetInput) (Asset, error)
	GetAssetForUser(ctx context.Context, userID string, assetID string) (Asset, error)
	GetTTSCache(ctx context.Context, cacheKey string, now time.Time) (TTSCacheEntry, error)
	SaveTTSCache(ctx context.Context, input SaveTTSCacheInput) (TTSCacheEntry, error)
	CleanupExpiredTTSCache(ctx context.Context, now time.Time) (int, error)
}
