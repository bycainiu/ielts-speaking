package auth

import (
	"context"
	"sync"
	"time"
)

type fakeStore struct {
	mu            sync.Mutex
	usersByID     map[string]UserWithPassword
	usersByEmail  map[string]string
	lastLoginHits int
}

func newFakeStore() *fakeStore {
	return &fakeStore{
		usersByID:    map[string]UserWithPassword{},
		usersByEmail: map[string]string{},
	}
}

func (s *fakeStore) CreateUser(_ context.Context, params CreateUserParams) (User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	email := normalizeEmail(params.Email)
	if _, exists := s.usersByEmail[email]; exists {
		return User{}, ErrEmailAlreadyRegistered
	}

	user := User{
		ID:        "user_001",
		Email:     email,
		Role:      "user",
		Status:    "active",
		CreatedAt: time.Now().UTC(),
	}
	s.usersByID[user.ID] = UserWithPassword{User: user, PasswordHash: params.PasswordHash}
	s.usersByEmail[email] = user.ID

	return user, nil
}

func (s *fakeStore) GetUserByEmail(_ context.Context, email string) (UserWithPassword, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	id, exists := s.usersByEmail[normalizeEmail(email)]
	if !exists {
		return UserWithPassword{}, ErrUserNotFound
	}
	return s.usersByID[id], nil
}

func (s *fakeStore) GetUserByID(_ context.Context, userID string) (User, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	user, exists := s.usersByID[userID]
	if !exists {
		return User{}, ErrUserNotFound
	}
	return user.User, nil
}

func (s *fakeStore) UpdateLastLogin(_ context.Context, userID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, exists := s.usersByID[userID]; !exists {
		return ErrUserNotFound
	}

	s.lastLoginHits++
	return nil
}

type fakeHasher struct{}

func (fakeHasher) Hash(password string) (string, error) {
	return "hashed:" + password, nil
}

func (fakeHasher) Compare(hash string, password string) error {
	if hash != "hashed:"+password {
		return ErrInvalidCredentials
	}
	return nil
}

func testTokenService(t testingT) TokenService {
	t.Helper()

	service, err := NewTokenService(TokenServiceConfig{
		Secret: "test-secret-must-be-at-least-32-bytes",
		Issuer: "test-api",
	})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}

	return service
}

type testingT interface {
	Helper()
	Fatalf(format string, args ...any)
}
