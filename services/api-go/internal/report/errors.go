package report

import "errors"

var (
	ErrNotFound     = errors.New("report resource not found")
	ErrInvalidInput = errors.New("invalid report input")
)
