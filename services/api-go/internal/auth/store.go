package auth

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
)

type Store interface {
	CreateUser(ctx context.Context, params CreateUserParams) (User, error)
	GetUserByEmail(ctx context.Context, email string) (UserWithPassword, error)
	GetUserByID(ctx context.Context, userID string) (User, error)
	UpdateLastLogin(ctx context.Context, userID string) error
}

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}

func (s PostgresStore) CreateUser(ctx context.Context, params CreateUserParams) (User, error) {
	email := normalizeEmail(params.Email)

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return User{}, fmt.Errorf("begin create user: %w", err)
	}
	defer tx.Rollback()

	var exists bool
	if err := tx.QueryRowContext(ctx, `select exists(select 1 from users where lower(email) = $1 and deleted_at is null)`, email).Scan(&exists); err != nil {
		return User{}, fmt.Errorf("check existing user: %w", err)
	}
	if exists {
		return User{}, ErrEmailAlreadyRegistered
	}

	user, err := scanUser(tx.QueryRowContext(ctx, `
		insert into users (email, password_hash)
		values ($1, $2)
		returning id::text, email, role::text, status::text, created_at
	`, email, params.PasswordHash))
	if err != nil {
		return User{}, fmt.Errorf("insert user: %w", err)
	}

	if _, err := tx.ExecContext(ctx, `
		insert into user_profiles (user_id, display_name)
		values ($1::uuid, nullif($2, ''))
	`, user.ID, strings.TrimSpace(params.DisplayName)); err != nil {
		return User{}, fmt.Errorf("insert user profile: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return User{}, fmt.Errorf("commit create user: %w", err)
	}

	return user, nil
}

func (s PostgresStore) GetUserByEmail(ctx context.Context, email string) (UserWithPassword, error) {
	row := s.db.QueryRowContext(ctx, `
		select id::text, email, role::text, status::text, created_at, password_hash
		from users
		where lower(email) = $1 and deleted_at is null
	`, normalizeEmail(email))

	return scanUserWithPassword(row)
}

func (s PostgresStore) GetUserByID(ctx context.Context, userID string) (User, error) {
	return scanUser(s.db.QueryRowContext(ctx, `
		select id::text, email, role::text, status::text, created_at
		from users
		where id = $1::uuid and deleted_at is null
	`, userID))
}

func (s PostgresStore) UpdateLastLogin(ctx context.Context, userID string) error {
	result, err := s.db.ExecContext(ctx, `
		update users
		set last_login_at = now()
		where id = $1::uuid and deleted_at is null
	`, userID)
	if err != nil {
		return fmt.Errorf("update last login: %w", err)
	}

	affected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("read rows affected: %w", err)
	}
	if affected == 0 {
		return ErrUserNotFound
	}

	return nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanUser(row rowScanner) (User, error) {
	var user User
	if err := row.Scan(&user.ID, &user.Email, &user.Role, &user.Status, &user.CreatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return User{}, ErrUserNotFound
		}
		return User{}, err
	}
	return user, nil
}

func scanUserWithPassword(row rowScanner) (UserWithPassword, error) {
	var user UserWithPassword
	if err := row.Scan(&user.ID, &user.Email, &user.Role, &user.Status, &user.CreatedAt, &user.PasswordHash); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return UserWithPassword{}, ErrUserNotFound
		}
		return UserWithPassword{}, err
	}
	return user, nil
}

func normalizeEmail(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}
