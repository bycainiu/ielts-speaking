package audio

import "errors"

var (
	ErrNotFound           = errors.New("audio asset not found")
	ErrInvalidInput       = errors.New("invalid audio input")
	ErrFileTooLarge       = errors.New("audio file too large")
	ErrDurationTooLong    = errors.New("audio duration too long")
	ErrUnsupportedType    = errors.New("unsupported audio file type")
	ErrDuplicateAsset     = errors.New("duplicate audio asset")
	ErrStorageUnavailable = errors.New("audio storage unavailable")
	ErrConsentRequired    = errors.New("recording consent required")
	ErrVoiceCloneDisabled = errors.New("voice clone disabled")
)
