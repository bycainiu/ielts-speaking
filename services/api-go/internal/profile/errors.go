package profile

import "errors"

var (
	ErrNotFound     = errors.New("profile resource not found")
	ErrInvalidInput = errors.New("invalid profile input")
)
