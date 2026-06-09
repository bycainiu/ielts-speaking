package auth

import "golang.org/x/crypto/bcrypt"

type PasswordHasher interface {
	Hash(password string) (string, error)
	Compare(hash string, password string) error
}

type BcryptPasswordHasher struct {
	Cost int
}

func NewBcryptPasswordHasher() BcryptPasswordHasher {
	return BcryptPasswordHasher{Cost: bcrypt.DefaultCost}
}

func (h BcryptPasswordHasher) Hash(password string) (string, error) {
	cost := h.Cost
	if cost == 0 {
		cost = bcrypt.DefaultCost
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(password), cost)
	if err != nil {
		return "", err
	}
	return string(hashed), nil
}

func (h BcryptPasswordHasher) Compare(hash string, password string) error {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
}
