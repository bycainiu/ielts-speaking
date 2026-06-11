package billing

import "errors"

var (
	ErrNotFound        = errors.New("billing: not found")
	ErrInvalidInput    = errors.New("billing: invalid input")
	ErrOrderNotPending = errors.New("billing: order not pending")
	ErrPlanInactive    = errors.New("billing: plan inactive")
	ErrDuplicateSlug   = errors.New("billing: duplicate slug")
)
