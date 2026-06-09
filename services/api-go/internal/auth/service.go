package auth

import (
	"context"
	"errors"
	"strings"
)

type Service struct {
	store  Store
	hasher PasswordHasher
	tokens TokenService
}

type RegisterInput struct {
	Email       string
	Password    string
	DisplayName string
}

type LoginInput struct {
	Email    string
	Password string
}

type AuthResponse struct {
	User  User      `json:"user"`
	Token TokenPair `json:"token"`
}

func NewService(store Store, hasher PasswordHasher, tokens TokenService) Service {
	return Service{store: store, hasher: hasher, tokens: tokens}
}

func (s Service) Register(ctx context.Context, input RegisterInput) (AuthResponse, error) {
	hashed, err := s.hasher.Hash(input.Password)
	if err != nil {
		return AuthResponse{}, err
	}

	user, err := s.store.CreateUser(ctx, CreateUserParams{
		Email:        input.Email,
		PasswordHash: hashed,
		DisplayName:  input.DisplayName,
	})
	if err != nil {
		return AuthResponse{}, err
	}

	token, err := s.tokens.GeneratePair(user)
	if err != nil {
		return AuthResponse{}, err
	}

	return AuthResponse{User: user, Token: token}, nil
}

func (s Service) Login(ctx context.Context, input LoginInput) (AuthResponse, error) {
	user, err := s.store.GetUserByEmail(ctx, input.Email)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			return AuthResponse{}, ErrInvalidCredentials
		}
		return AuthResponse{}, err
	}
	if user.Status != "active" {
		return AuthResponse{}, ErrForbiddenUserStatus
	}

	if err := s.hasher.Compare(user.PasswordHash, input.Password); err != nil {
		return AuthResponse{}, ErrInvalidCredentials
	}

	if err := s.store.UpdateLastLogin(ctx, user.ID); err != nil && !errors.Is(err, ErrUserNotFound) {
		return AuthResponse{}, err
	}

	token, err := s.tokens.GeneratePair(user.User)
	if err != nil {
		return AuthResponse{}, err
	}

	return AuthResponse{User: user.User, Token: token}, nil
}

func (s Service) Refresh(ctx context.Context, refreshToken string) (AuthResponse, error) {
	claims, err := s.tokens.Parse(refreshToken, TokenTypeRefresh)
	if err != nil {
		return AuthResponse{}, err
	}

	user, err := s.store.GetUserByID(ctx, claims.UserID)
	if err != nil {
		return AuthResponse{}, err
	}
	if user.Status != "active" {
		return AuthResponse{}, ErrForbiddenUserStatus
	}

	token, err := s.tokens.GeneratePair(user)
	if err != nil {
		return AuthResponse{}, err
	}

	return AuthResponse{User: user, Token: token}, nil
}

func (s Service) CurrentUser(ctx context.Context, userID string) (User, error) {
	user, err := s.store.GetUserByID(ctx, userID)
	if err != nil {
		return User{}, err
	}
	if user.Status != "active" {
		return User{}, ErrForbiddenUserStatus
	}
	return user, nil
}

type Authenticator struct {
	store  Store
	tokens TokenService
}

func NewAuthenticator(store Store, tokens TokenService) Authenticator {
	return Authenticator{store: store, tokens: tokens}
}

func (a Authenticator) AuthenticateBearer(ctx context.Context, authHeader string) (AuthenticatedUser, error) {
	tokenString, ok := ExtractBearerToken(authHeader)
	if !ok {
		return AuthenticatedUser{}, ErrInvalidToken
	}

	claims, err := a.tokens.Parse(tokenString, TokenTypeAccess)
	if err != nil {
		return AuthenticatedUser{}, err
	}

	user, err := a.store.GetUserByID(ctx, claims.UserID)
	if err != nil {
		return AuthenticatedUser{}, err
	}
	if user.Status != "active" {
		return AuthenticatedUser{}, ErrForbiddenUserStatus
	}

	return AuthenticatedUser{
		ID:     user.ID,
		Email:  user.Email,
		Role:   user.Role,
		Status: user.Status,
	}, nil
}

func ExtractBearerToken(authHeader string) (string, bool) {
	authHeader = strings.TrimSpace(authHeader)
	const prefix = "Bearer "
	if len(authHeader) <= len(prefix) || !strings.EqualFold(authHeader[:len(prefix)], prefix) {
		return "", false
	}

	token := strings.TrimSpace(authHeader[len(prefix):])
	return token, token != ""
}
