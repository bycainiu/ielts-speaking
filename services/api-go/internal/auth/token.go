package auth

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	TokenTypeAccess  = "access"
	TokenTypeRefresh = "refresh"
)

type TokenService struct {
	secret     []byte
	issuer     string
	accessTTL  time.Duration
	refreshTTL time.Duration
	now        func() time.Time
}

type TokenServiceConfig struct {
	Secret     string
	Issuer     string
	AccessTTL  time.Duration
	RefreshTTL time.Duration
	Now        func() time.Time
}

type Claims struct {
	UserID    string `json:"user_id"`
	Email     string `json:"email"`
	Role      string `json:"role"`
	TokenType string `json:"token_type"`
	jwt.RegisteredClaims
}

func NewTokenService(cfg TokenServiceConfig) (TokenService, error) {
	if len(cfg.Secret) < 32 {
		return TokenService{}, errors.New("JWT secret 长度不能少于 32 个字符")
	}
	if cfg.Issuer == "" {
		cfg.Issuer = "ielts-speaking-api"
	}
	if cfg.AccessTTL == 0 {
		cfg.AccessTTL = 15 * time.Minute
	}
	if cfg.RefreshTTL == 0 {
		cfg.RefreshTTL = 7 * 24 * time.Hour
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}

	return TokenService{
		secret:     []byte(cfg.Secret),
		issuer:     cfg.Issuer,
		accessTTL:  cfg.AccessTTL,
		refreshTTL: cfg.RefreshTTL,
		now:        cfg.Now,
	}, nil
}

func (s TokenService) GeneratePair(user User) (TokenPair, error) {
	access, accessExpiresAt, err := s.generate(user, TokenTypeAccess, s.accessTTL)
	if err != nil {
		return TokenPair{}, err
	}

	refresh, _, err := s.generate(user, TokenTypeRefresh, s.refreshTTL)
	if err != nil {
		return TokenPair{}, err
	}

	return TokenPair{
		AccessToken:  access,
		RefreshToken: refresh,
		TokenType:    "Bearer",
		ExpiresAt:    accessExpiresAt,
	}, nil
}

func (s TokenService) Parse(tokenString string, expectedType string) (*Claims, error) {
	tokenString = strings.TrimSpace(tokenString)
	if tokenString == "" {
		return nil, ErrInvalidToken
	}

	claims := &Claims{}
	token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method %s", token.Header["alg"])
		}
		return s.secret, nil
	}, jwt.WithIssuer(s.issuer))
	if err != nil || !token.Valid {
		return nil, ErrInvalidToken
	}

	if claims.TokenType != expectedType {
		return nil, ErrInvalidToken
	}

	if claims.UserID == "" || claims.Email == "" {
		return nil, ErrInvalidToken
	}

	return claims, nil
}

func (s TokenService) generate(user User, tokenType string, ttl time.Duration) (string, time.Time, error) {
	now := s.now().UTC()
	expiresAt := now.Add(ttl)

	claims := Claims{
		UserID:    user.ID,
		Email:     user.Email,
		Role:      user.Role,
		TokenType: tokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    s.issuer,
			Subject:   user.ID,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(expiresAt),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(s.secret)
	if err != nil {
		return "", time.Time{}, err
	}

	return signed, expiresAt, nil
}
