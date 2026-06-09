package questionbank

import "errors"

var (
	ErrNotFound          = errors.New("question bank resource not found")
	ErrInvalidInput      = errors.New("invalid question bank input")
	ErrDuplicateResource = errors.New("duplicate question bank resource")
)
