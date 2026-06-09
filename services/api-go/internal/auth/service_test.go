package auth

import (
	"context"
	"errors"
	"testing"
)

func TestServiceRegisterCreatesUserAndTokenPair(t *testing.T) {
	store := newFakeStore()
	service := NewService(store, fakeHasher{}, testTokenService(t))

	response, err := service.Register(context.Background(), RegisterInput{
		Email:       "Learner@Example.COM",
		Password:    "secret-password",
		DisplayName: "Learner",
	})
	if err != nil {
		t.Fatalf("Register() error = %v", err)
	}

	if response.User.Email != "learner@example.com" {
		t.Fatalf("email = %q, want normalized email", response.User.Email)
	}
	if response.Token.AccessToken == "" || response.Token.RefreshToken == "" {
		t.Fatal("expected access and refresh tokens")
	}

	stored, err := store.GetUserByEmail(context.Background(), "learner@example.com")
	if err != nil {
		t.Fatalf("GetUserByEmail() error = %v", err)
	}
	if stored.PasswordHash != "hashed:secret-password" {
		t.Fatalf("password hash = %q", stored.PasswordHash)
	}
}

func TestServiceLoginRejectsWrongPassword(t *testing.T) {
	store := newFakeStore()
	service := NewService(store, fakeHasher{}, testTokenService(t))
	if _, err := service.Register(context.Background(), RegisterInput{Email: "learner@example.com", Password: "secret-password"}); err != nil {
		t.Fatalf("Register() error = %v", err)
	}

	_, err := service.Login(context.Background(), LoginInput{Email: "learner@example.com", Password: "wrong-password"})
	if !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("Login() error = %v, want ErrInvalidCredentials", err)
	}
}

func TestServiceRefreshRejectsAccessToken(t *testing.T) {
	store := newFakeStore()
	service := NewService(store, fakeHasher{}, testTokenService(t))
	response, err := service.Register(context.Background(), RegisterInput{Email: "learner@example.com", Password: "secret-password"})
	if err != nil {
		t.Fatalf("Register() error = %v", err)
	}

	_, err = service.Refresh(context.Background(), response.Token.AccessToken)
	if !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("Refresh() error = %v, want ErrInvalidToken", err)
	}
}

func TestAuthenticatorAuthenticatesBearerAccessToken(t *testing.T) {
	store := newFakeStore()
	tokens := testTokenService(t)
	service := NewService(store, fakeHasher{}, tokens)
	response, err := service.Register(context.Background(), RegisterInput{Email: "learner@example.com", Password: "secret-password"})
	if err != nil {
		t.Fatalf("Register() error = %v", err)
	}

	authenticator := NewAuthenticator(store, tokens)
	user, err := authenticator.AuthenticateBearer(context.Background(), "Bearer "+response.Token.AccessToken)
	if err != nil {
		t.Fatalf("AuthenticateBearer() error = %v", err)
	}

	if user.ID != response.User.ID || user.Email != response.User.Email {
		t.Fatalf("authenticated user = %+v, want %+v", user, response.User)
	}
}
