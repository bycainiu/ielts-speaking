package adminops

import "errors"

var (
	ErrNotFound     = errors.New("admin content resource not found")
	ErrInvalidInput = errors.New("invalid admin content input")
)
