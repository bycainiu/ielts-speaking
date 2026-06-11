-- +goose NO TRANSACTION
-- +goose Up
ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'paused' AFTER 'in_progress';

-- +goose Down
-- PostgreSQL does not support dropping enum values safely in-place.
SELECT 1;
