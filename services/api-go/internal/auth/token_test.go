package auth

import (
	"errors"
	"testing"
)

func TestTokenServiceParsesExpectedTokenType(t *testing.T) {
	tokens := testTokenService(t)
	user := User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active"}

	pair, err := tokens.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	claims, err := tokens.Parse(pair.AccessToken, TokenTypeAccess)
	if err != nil {
		t.Fatalf("Parse(access) error = %v", err)
	}
	if claims.UserID != user.ID || claims.Email != user.Email {
		t.Fatalf("claims = %+v, want user id/email", claims)
	}

	_, err = tokens.Parse(pair.AccessToken, TokenTypeRefresh)
	if !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("Parse(access as refresh) error = %v, want ErrInvalidToken", err)
	}
}

func TestExtractBearerToken(t *testing.T) {
	token, ok := ExtractBearerToken("Bearer abc.def")
	if !ok || token != "abc.def" {
		t.Fatalf("ExtractBearerToken() = %q, %v", token, ok)
	}

	if _, ok := ExtractBearerToken("Basic abc.def"); ok {
		t.Fatal("ExtractBearerToken() accepted non-bearer token")
	}
}
