package session

import "errors"

var (
	ErrNotFound            = errors.New("session resource not found")
	ErrInvalidInput        = errors.New("invalid session input")
	ErrInvalidStatusFlow   = errors.New("invalid session status flow")
	ErrDuplicateTurnIndex  = errors.New("duplicate session turn index")
	ErrDuplicateAudioAsset = errors.New("duplicate audio asset")
)
