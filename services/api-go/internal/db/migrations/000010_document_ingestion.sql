-- +goose Up
ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS run_kind text NOT NULL DEFAULT 'session_workflow',
    ADD COLUMN IF NOT EXISTS subject_type text,
    ADD COLUMN IF NOT EXISTS subject_id text;

CREATE INDEX IF NOT EXISTS agent_runs_kind_started_idx ON agent_runs (run_kind, started_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_subject_idx ON agent_runs (subject_type, subject_id, started_at DESC);

ALTER TABLE agent_steps
    ADD COLUMN IF NOT EXISTS part smallint CHECK (part IS NULL OR part BETWEEN 1 AND 3),
    ADD COLUMN IF NOT EXISTS question_id text,
    ADD COLUMN IF NOT EXISTS execution_kind text NOT NULL DEFAULT 'deterministic',
    ADD COLUMN IF NOT EXISTS input_payload jsonb,
    ADD COLUMN IF NOT EXISTS input_detail jsonb,
    ADD COLUMN IF NOT EXISTS output_payload jsonb,
    ADD COLUMN IF NOT EXISTS messages jsonb,
    ADD COLUMN IF NOT EXISTS retrieved_chunks jsonb,
    ADD COLUMN IF NOT EXISTS structured_output_validity boolean,
    ADD COLUMN IF NOT EXISTS scoring_result jsonb,
    ADD COLUMN IF NOT EXISTS error_type text,
    ADD COLUMN IF NOT EXISTS input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
    ADD COLUMN IF NOT EXISTS output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
    ADD COLUMN IF NOT EXISTS estimated_cost_usd numeric(12, 6) CHECK (estimated_cost_usd IS NULL OR estimated_cost_usd >= 0);

ALTER TABLE model_calls
    ADD COLUMN IF NOT EXISTS step_id uuid REFERENCES agent_steps(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS call_name text,
    ADD COLUMN IF NOT EXISTS agent_name text,
    ADD COLUMN IF NOT EXISTS execution_kind text,
    ADD COLUMN IF NOT EXISTS payload_origin text,
    ADD COLUMN IF NOT EXISTS prompt_version text,
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS request_payload jsonb,
    ADD COLUMN IF NOT EXISTS response_payload jsonb;

CREATE INDEX IF NOT EXISTS model_calls_step_idx ON model_calls (step_id, created_at DESC);

CREATE TABLE agent_run_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE SET NULL,
    event_index integer NOT NULL CHECK (event_index >= 0),
    event_type text NOT NULL,
    title text,
    summary text,
    visibility text NOT NULL DEFAULT 'default',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, event_index),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX agent_run_events_run_idx ON agent_run_events (run_id, event_index);

CREATE TABLE agent_run_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    step_id uuid REFERENCES agent_steps(id) ON DELETE SET NULL,
    artifact_kind text NOT NULL,
    title text NOT NULL,
    content_type text NOT NULL,
    storage_bucket text,
    storage_key text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    inline_text text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX agent_run_artifacts_run_idx ON agent_run_artifacts (run_id, created_at);

CREATE TABLE knowledge_source_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    visibility text NOT NULL,
    upload_purpose text NOT NULL DEFAULT 'mixed',
    title text NOT NULL,
    original_filename text NOT NULL,
    extension text NOT NULL,
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    checksum_sha256 text NOT NULL,
    storage_bucket text NOT NULL,
    storage_key text NOT NULL UNIQUE,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (visibility IN ('private', 'public')),
    CHECK (upload_purpose IN ('auto', 'question_bank', 'knowledge', 'background', 'mixed')),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_source_files_owner_created_idx ON knowledge_source_files (owner_user_id, created_at DESC);
CREATE INDEX knowledge_source_files_visibility_checksum_idx ON knowledge_source_files (visibility, checksum_sha256);

CREATE TABLE knowledge_ingestion_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file_id uuid NOT NULL REFERENCES knowledge_source_files(id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    requested_visibility text NOT NULL,
    requested_action text NOT NULL DEFAULT 'auto',
    status text NOT NULL DEFAULT 'queued',
    stage text NOT NULL DEFAULT 'queued',
    priority integer NOT NULL DEFAULT 0,
    progress_pct integer NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    classifier_label text,
    classifier_confidence numeric(5, 4) CHECK (classifier_confidence IS NULL OR (classifier_confidence >= 0 AND classifier_confidence <= 1)),
    run_id text REFERENCES agent_runs(id) ON DELETE SET NULL,
    error_code text,
    error_message text,
    duplicate_of_job_id uuid REFERENCES knowledge_ingestion_jobs(id) ON DELETE SET NULL,
    cancel_requested_at timestamptz,
    queued_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    heartbeat_at timestamptz,
    finished_at timestamptz,
    materialized_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (requested_visibility IN ('private', 'public')),
    CHECK (requested_action IN ('auto', 'question_bank', 'knowledge', 'background', 'mixed')),
    CHECK (status IN ('queued', 'running', 'awaiting_review', 'awaiting_user_confirmation', 'completed', 'failed', 'cancelled', 'rejected')),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_ingestion_jobs_queue_idx ON knowledge_ingestion_jobs (status, priority DESC, queued_at ASC);
CREATE INDEX knowledge_ingestion_jobs_owner_created_idx ON knowledge_ingestion_jobs (owner_user_id, queued_at DESC);
CREATE INDEX knowledge_ingestion_jobs_run_idx ON knowledge_ingestion_jobs (run_id);

CREATE TABLE knowledge_ingestion_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES knowledge_ingestion_jobs(id) ON DELETE CASCADE,
    candidate_kind text NOT NULL,
    title text NOT NULL,
    summary text,
    content text NOT NULL,
    candidate_status text NOT NULL DEFAULT 'pending',
    normalized_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    materialization_plan jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (candidate_kind IN ('question', 'knowledge', 'background')),
    CHECK (candidate_status IN ('pending', 'approved', 'rejected', 'confirmed', 'materialized')),
    CHECK (jsonb_typeof(normalized_payload) = 'object'),
    CHECK (jsonb_typeof(materialization_plan) = 'object'),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_ingestion_candidates_job_kind_idx ON knowledge_ingestion_candidates (job_id, candidate_kind, candidate_status);

CREATE TABLE knowledge_ingestion_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES knowledge_ingestion_jobs(id) ON DELETE CASCADE,
    candidate_id uuid REFERENCES knowledge_ingestion_candidates(id) ON DELETE SET NULL,
    reviewer_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reviewer_role text NOT NULL,
    decision text NOT NULL,
    notes text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (reviewer_role IN ('user', 'operator', 'admin')),
    CHECK (decision IN ('approve', 'reject', 'confirm', 'retry', 'cancel')),
    CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX knowledge_ingestion_reviews_job_created_idx ON knowledge_ingestion_reviews (job_id, created_at DESC);

CREATE TABLE knowledge_ingestion_artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES knowledge_ingestion_jobs(id) ON DELETE CASCADE,
    run_id text REFERENCES agent_runs(id) ON DELETE SET NULL,
    artifact_kind text NOT NULL,
    title text NOT NULL,
    content_type text NOT NULL,
    storage_bucket text,
    storage_key text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    inline_text text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (artifact_kind IN ('original', 'extracted_text', 'normalized_text', 'command_output', 'preview', 'candidate_export', 'materialization_simulation')),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_ingestion_artifacts_job_created_idx ON knowledge_ingestion_artifacts (job_id, created_at);

CREATE TABLE agent_runtime_policies (
    policy_key text PRIMARY KEY,
    policy_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(policy_value) = 'object')
);

INSERT INTO agent_runtime_policies (policy_key, policy_value)
VALUES ('document_ingestion', '{"max_concurrency": 2, "paused": false}'::jsonb)
ON CONFLICT (policy_key) DO NOTHING;

CREATE TRIGGER knowledge_ingestion_jobs_set_updated_at BEFORE UPDATE ON knowledge_ingestion_jobs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER knowledge_ingestion_candidates_set_updated_at BEFORE UPDATE ON knowledge_ingestion_candidates FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TRIGGER IF EXISTS knowledge_ingestion_candidates_set_updated_at ON knowledge_ingestion_candidates;
DROP TRIGGER IF EXISTS knowledge_ingestion_jobs_set_updated_at ON knowledge_ingestion_jobs;

DELETE FROM agent_runtime_policies WHERE policy_key = 'document_ingestion';
DROP TABLE IF EXISTS agent_runtime_policies;
DROP TABLE IF EXISTS knowledge_ingestion_artifacts;
DROP TABLE IF EXISTS knowledge_ingestion_reviews;
DROP TABLE IF EXISTS knowledge_ingestion_candidates;
DROP TABLE IF EXISTS knowledge_ingestion_jobs;
DROP TABLE IF EXISTS knowledge_source_files;
DROP TABLE IF EXISTS agent_run_artifacts;
DROP TABLE IF EXISTS agent_run_events;

DROP INDEX IF EXISTS model_calls_step_idx;
ALTER TABLE model_calls
    DROP COLUMN IF EXISTS response_payload,
    DROP COLUMN IF EXISTS request_payload,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS prompt_version,
    DROP COLUMN IF EXISTS payload_origin,
    DROP COLUMN IF EXISTS execution_kind,
    DROP COLUMN IF EXISTS agent_name,
    DROP COLUMN IF EXISTS call_name,
    DROP COLUMN IF EXISTS step_id;

ALTER TABLE agent_steps
    DROP COLUMN IF EXISTS estimated_cost_usd,
    DROP COLUMN IF EXISTS output_tokens,
    DROP COLUMN IF EXISTS input_tokens,
    DROP COLUMN IF EXISTS error_type,
    DROP COLUMN IF EXISTS scoring_result,
    DROP COLUMN IF EXISTS structured_output_validity,
    DROP COLUMN IF EXISTS retrieved_chunks,
    DROP COLUMN IF EXISTS messages,
    DROP COLUMN IF EXISTS output_payload,
    DROP COLUMN IF EXISTS input_detail,
    DROP COLUMN IF EXISTS input_payload,
    DROP COLUMN IF EXISTS execution_kind,
    DROP COLUMN IF EXISTS question_id,
    DROP COLUMN IF EXISTS part;

DROP INDEX IF EXISTS agent_runs_subject_idx;
DROP INDEX IF EXISTS agent_runs_kind_started_idx;
ALTER TABLE agent_runs
    DROP COLUMN IF EXISTS subject_id,
    DROP COLUMN IF EXISTS subject_type,
    DROP COLUMN IF EXISTS run_kind;
