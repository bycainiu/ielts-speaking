package realtime

import (
	"context"
	"database/sql"
)

type SessionAccessStore interface {
	EnsureSessionAccess(ctx context.Context, userID string, sessionID string) error
}

type PostgresSessionAccessStore struct {
	db *sql.DB
}

func NewPostgresSessionAccessStore(db *sql.DB) PostgresSessionAccessStore {
	return PostgresSessionAccessStore{db: db}
}

func (s PostgresSessionAccessStore) EnsureSessionAccess(ctx context.Context, userID string, sessionID string) error {
	var exists bool
	if err := s.db.QueryRowContext(ctx, `
		select exists(
			select 1
			from practice_sessions
			where id = $1::uuid and user_id = $2::uuid and deleted_at is null
		)
	`, sessionID, userID).Scan(&exists); err != nil {
		return err
	}
	if !exists {
		return ErrSessionNotFound
	}
	return nil
}
