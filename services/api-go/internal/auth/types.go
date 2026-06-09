package auth

import "time"

type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Role      string    `json:"role"`
	Status    string    `json:"status"`
	CreatedAt time.Time `json:"created_at"`
}

type UserWithPassword struct {
	User
	PasswordHash string
}

type CreateUserParams struct {
	Email        string
	PasswordHash string
	DisplayName  string
}

type TokenPair struct {
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token"`
	TokenType    string    `json:"token_type"`
	ExpiresAt    time.Time `json:"expires_at"`
}

type AuthenticatedUser struct {
	ID     string
	Email  string
	Role   string
	Status string
}
