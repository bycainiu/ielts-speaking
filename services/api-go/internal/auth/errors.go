package auth

import "errors"

var (
	ErrEmailAlreadyRegistered = errors.New("email already registered")
	ErrInvalidCredentials     = errors.New("invalid credentials")
	ErrInvalidToken           = errors.New("invalid token")
	ErrForbiddenUserStatus    = errors.New("forbidden user status")
	ErrUserNotFound           = errors.New("user not found")
)
