package knowledgeingestion

import (
	"errors"
)

var (
	ErrNotFound           = errors.New("knowledge ingestion resource not found")
	ErrInvalidInput       = errors.New("knowledge ingestion input invalid")
	ErrForbidden          = errors.New("knowledge ingestion access forbidden")
	ErrConflict           = errors.New("knowledge ingestion conflict")
	ErrStorageUnavailable = errors.New("knowledge ingestion storage unavailable")
	ErrUnsupportedType    = errors.New("knowledge ingestion file type unsupported")
	ErrFileTooLarge       = errors.New("knowledge ingestion file too large")
	ErrProcessingPending  = errors.New("knowledge ingestion processing still pending")
)
