-- +goose Up
CREATE TABLE report_user_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL REFERENCES score_reports(id) ON DELETE CASCADE,
    session_id uuid NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type text NOT NULL CHECK (target_type IN ('overall', 'score', 'feedback', 'reference_answer')),
    target_id uuid,
    vote text NOT NULL CHECK (vote IN ('up', 'down')),
    comment text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (target_type = 'overall' AND target_id IS NULL)
        OR (target_type <> 'overall' AND target_id IS NOT NULL)
    ),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX report_user_feedback_report_idx ON report_user_feedback (report_id, created_at DESC);
CREATE INDEX report_user_feedback_session_idx ON report_user_feedback (session_id, created_at DESC);
CREATE INDEX report_user_feedback_user_idx ON report_user_feedback (user_id, created_at DESC);
CREATE INDEX report_user_feedback_vote_idx ON report_user_feedback (vote, target_type, created_at DESC);

-- +goose Down
DROP TABLE IF EXISTS report_user_feedback;
