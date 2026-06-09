package realtime

import "errors"

var (
	ErrInvalidEvent    = errors.New("invalid realtime event")
	ErrSessionNotFound = errors.New("realtime session not found")
	ErrUnauthorized    = errors.New("realtime unauthorized")
)
