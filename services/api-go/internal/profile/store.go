package profile

import "context"

type Store interface {
	GetBackground(ctx context.Context, userID string) (Background, error)
	SaveBackground(ctx context.Context, userID string, input BackgroundInput) (Background, error)
}
