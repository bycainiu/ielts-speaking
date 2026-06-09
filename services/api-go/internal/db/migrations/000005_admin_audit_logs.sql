-- +goose Up

CREATE TABLE admin_audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    actor_role text NOT NULL,
    action text NOT NULL,
    resource text NOT NULL,
    method text NOT NULL,
    path text NOT NULL,
    status_code integer NOT NULL CHECK (status_code BETWEEN 100 AND 599),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX admin_audit_logs_actor_idx ON admin_audit_logs (actor_user_id, created_at DESC);
CREATE INDEX admin_audit_logs_resource_idx ON admin_audit_logs (resource, created_at DESC);
CREATE INDEX admin_audit_logs_status_idx ON admin_audit_logs (status_code, created_at DESC);

-- +goose Down

DROP TABLE IF EXISTS admin_audit_logs;
