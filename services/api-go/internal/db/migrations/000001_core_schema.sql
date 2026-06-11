-- +goose Up
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE user_role AS ENUM ('user', 'operator', 'admin');
CREATE TYPE user_status AS ENUM ('active', 'disabled', 'deleted');
CREATE TYPE content_status AS ENUM ('draft', 'reviewing', 'active', 'archived');
CREATE TYPE source_type AS ENUM ('original', 'authorized', 'user_recall', 'internal');
CREATE TYPE session_mode AS ENUM ('full_exam', 'part_practice', 'topic_practice');
CREATE TYPE session_status AS ENUM ('created', 'planned', 'in_progress', 'paused', 'scoring', 'completed', 'cancelled', 'failed');
CREATE TYPE turn_status AS ENUM ('pending', 'recording', 'asr_processing', 'completed', 'failed');
CREATE TYPE audio_kind AS ENUM ('user_recording', 'examiner_tts', 'reference');
CREATE TYPE report_status AS ENUM ('generating', 'ready', 'failed');
CREATE TYPE scoring_criterion AS ENUM (
    'fluency_coherence',
    'lexical_resource',
    'grammatical_range_accuracy',
    'pronunciation'
);
CREATE TYPE knowledge_doc_type AS ENUM (
    'question_bank',
    'rubric',
    'user_profile',
    'topic_knowledge',
    'review_history'
);

-- +goose StatementBegin
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    password_hash text NOT NULL,
    role user_role NOT NULL DEFAULT 'user',
    status user_status NOT NULL DEFAULT 'active',
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (position('@' in email) > 1)
);

CREATE UNIQUE INDEX users_email_active_uidx ON users (lower(email)) WHERE deleted_at IS NULL;

CREATE TABLE user_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name text,
    timezone text NOT NULL DEFAULT 'Asia/Shanghai',
    target_band numeric(2, 1) CHECK (target_band IS NULL OR target_band BETWEEN 0 AND 9),
    current_band numeric(2, 1) CHECK (current_band IS NULL OR current_band BETWEEN 0 AND 9),
    preferred_exam_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (user_id)
);

CREATE TABLE background_questionnaires (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version integer NOT NULL DEFAULT 1,
    answers jsonb NOT NULL DEFAULT '{}'::jsonb,
    privacy_exclusions jsonb NOT NULL DEFAULT '[]'::jsonb,
    submitted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(answers) = 'object'),
    CHECK (jsonb_typeof(privacy_exclusions) = 'array')
);

CREATE INDEX background_questionnaires_user_idx ON background_questionnaires (user_id, created_at DESC);

CREATE TABLE background_facts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    questionnaire_id uuid REFERENCES background_questionnaires(id) ON DELETE SET NULL,
    topic text,
    fact_key text NOT NULL,
    fact_value text NOT NULL,
    privacy_level text NOT NULL DEFAULT 'normal',
    allowed_usage text[] NOT NULL DEFAULT ARRAY['question_personalization', 'feedback_personalization'],
    is_excluded boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX background_facts_user_topic_idx ON background_facts (user_id, topic) WHERE is_excluded = false;

CREATE TABLE consent_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type text NOT NULL,
    version text NOT NULL,
    accepted boolean NOT NULL,
    accepted_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX consent_records_user_type_idx ON consent_records (user_id, consent_type, created_at DESC);

CREATE TABLE seasons (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    title text NOT NULL,
    starts_on date,
    ends_on date,
    status content_status NOT NULL DEFAULT 'draft',
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX seasons_single_active_uidx ON seasons (is_active) WHERE is_active = true AND status = 'active' AND deleted_at IS NULL;

CREATE TABLE topic_categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE topics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id uuid REFERENCES topic_categories(id) ON DELETE SET NULL,
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    status content_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE INDEX topics_category_status_idx ON topics (category_id, status);

CREATE TABLE questions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id uuid REFERENCES seasons(id) ON DELETE SET NULL,
    topic_id uuid REFERENCES topics(id) ON DELETE SET NULL,
    part smallint NOT NULL CHECK (part BETWEEN 1 AND 3),
    text text NOT NULL,
    difficulty smallint CHECK (difficulty IS NULL OR difficulty BETWEEN 1 AND 5),
    source_type source_type NOT NULL DEFAULT 'original',
    license text,
    review_status content_status NOT NULL DEFAULT 'draft',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX questions_part_status_idx ON questions (part, review_status) WHERE deleted_at IS NULL;
CREATE INDEX questions_season_topic_idx ON questions (season_id, topic_id) WHERE deleted_at IS NULL;

CREATE TABLE cue_cards (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id uuid NOT NULL UNIQUE REFERENCES questions(id) ON DELETE CASCADE,
    prompt text NOT NULL,
    bullet_points text[] NOT NULL DEFAULT '{}',
    preparation_seconds integer NOT NULL DEFAULT 60 CHECK (preparation_seconds BETWEEN 0 AND 120),
    speaking_seconds integer NOT NULL DEFAULT 120 CHECK (speaking_seconds BETWEEN 60 AND 240),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE followup_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id uuid REFERENCES questions(id) ON DELETE CASCADE,
    part smallint NOT NULL CHECK (part BETWEEN 1 AND 3),
    text text NOT NULL,
    trigger_hint text,
    sort_order integer NOT NULL DEFAULT 0,
    review_status content_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX followup_templates_question_idx ON followup_templates (question_id, sort_order);

CREATE TABLE question_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id uuid NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    version integer NOT NULL,
    snapshot jsonb NOT NULL,
    changed_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (question_id, version),
    CHECK (jsonb_typeof(snapshot) = 'object')
);

CREATE TABLE knowledge_docs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type knowledge_doc_type NOT NULL,
    owner_user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    source_id uuid,
    title text NOT NULL,
    content_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    status content_status NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_docs_type_status_idx ON knowledge_docs (doc_type, status) WHERE deleted_at IS NULL;
CREATE INDEX knowledge_docs_owner_idx ON knowledge_docs (owner_user_id) WHERE owner_user_id IS NOT NULL;

CREATE TABLE knowledge_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id uuid NOT NULL REFERENCES knowledge_docs(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    content text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(1536),
    embedding_model text,
    token_count integer CHECK (token_count IS NULL OR token_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_id, chunk_index),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX knowledge_chunks_metadata_gin_idx ON knowledge_chunks USING gin (metadata);
CREATE INDEX knowledge_chunks_doc_idx ON knowledge_chunks (doc_id, chunk_index);
CREATE INDEX knowledge_chunks_part_idx ON knowledge_chunks ((metadata->>'part')) WHERE metadata ? 'part';
CREATE INDEX knowledge_chunks_season_idx ON knowledge_chunks ((metadata->>'season_id')) WHERE metadata ? 'season_id';
CREATE INDEX knowledge_chunks_embedding_idx ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100) WHERE embedding IS NOT NULL;

CREATE TABLE practice_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode session_mode NOT NULL,
    status session_status NOT NULL DEFAULT 'created',
    season_id uuid REFERENCES seasons(id) ON DELETE SET NULL,
    topic_id uuid REFERENCES topics(id) ON DELETE SET NULL,
    target_part smallint CHECK (target_part IS NULL OR target_part BETWEEN 1 AND 3),
    state jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    CHECK (jsonb_typeof(state) = 'object')
);

CREATE INDEX practice_sessions_user_status_idx ON practice_sessions (user_id, status, created_at DESC);
CREATE INDEX practice_sessions_mode_idx ON practice_sessions (mode, created_at DESC);

CREATE TABLE session_parts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    part smallint NOT NULL CHECK (part BETWEEN 1 AND 3),
    status session_status NOT NULL DEFAULT 'created',
    order_index integer NOT NULL DEFAULT 0,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, part)
);

CREATE TABLE session_turns (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    part_id uuid REFERENCES session_parts(id) ON DELETE SET NULL,
    question_id uuid REFERENCES questions(id) ON DELETE SET NULL,
    turn_index integer NOT NULL CHECK (turn_index >= 0),
    speaker text NOT NULL CHECK (speaker IN ('examiner', 'user')),
    status turn_status NOT NULL DEFAULT 'pending',
    question_text text,
    answer_text text,
    agent_run_id text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_index),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX session_turns_session_idx ON session_turns (session_id, turn_index);
CREATE INDEX session_turns_question_idx ON session_turns (question_id) WHERE question_id IS NOT NULL;

CREATE TABLE audio_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    session_id uuid REFERENCES practice_sessions(id) ON DELETE CASCADE,
    turn_id uuid REFERENCES session_turns(id) ON DELETE SET NULL,
    kind audio_kind NOT NULL,
    storage_bucket text NOT NULL,
    storage_key text NOT NULL,
    mime_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
    checksum_sha256 text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (storage_bucket, storage_key)
);

CREATE INDEX audio_assets_session_idx ON audio_assets (session_id, created_at DESC);
CREATE INDEX audio_assets_turn_idx ON audio_assets (turn_id) WHERE turn_id IS NOT NULL;

CREATE TABLE asr_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id uuid NOT NULL REFERENCES session_turns(id) ON DELETE CASCADE,
    audio_asset_id uuid REFERENCES audio_assets(id) ON DELETE SET NULL,
    provider text NOT NULL,
    model text NOT NULL,
    transcript text NOT NULL,
    confidence numeric(4, 3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    segments jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(segments) = 'array')
);

CREATE INDEX asr_results_turn_idx ON asr_results (turn_id, created_at DESC);

CREATE TABLE speech_metrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id uuid NOT NULL REFERENCES session_turns(id) ON DELETE CASCADE,
    audio_asset_id uuid REFERENCES audio_assets(id) ON DELETE SET NULL,
    wpm numeric(6, 2) CHECK (wpm IS NULL OR wpm >= 0),
    long_pause_count integer CHECK (long_pause_count IS NULL OR long_pause_count >= 0),
    filler_ratio numeric(5, 4) CHECK (filler_ratio IS NULL OR filler_ratio BETWEEN 0 AND 1),
    asr_confidence numeric(4, 3) CHECK (asr_confidence IS NULL OR asr_confidence BETWEEN 0 AND 1),
    raw_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(raw_metrics) = 'object')
);

CREATE INDEX speech_metrics_turn_idx ON speech_metrics (turn_id, created_at DESC);

CREATE TABLE agent_runs (
    id text PRIMARY KEY,
    session_id uuid REFERENCES practice_sessions(id) ON DELETE SET NULL,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    mode session_mode,
    status text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX agent_runs_session_idx ON agent_runs (session_id, started_at DESC);

ALTER TABLE session_turns
    ADD CONSTRAINT session_turns_agent_run_fk
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL;

CREATE TABLE agent_steps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    workflow_node text NOT NULL,
    agent_name text,
    prompt_version text,
    model_name text,
    status text NOT NULL,
    input_summary text,
    output_summary text,
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    error_code text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE INDEX agent_steps_run_idx ON agent_steps (run_id, started_at);

CREATE TABLE model_calls (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid REFERENCES practice_sessions(id) ON DELETE SET NULL,
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    agent_run_id text REFERENCES agent_runs(id) ON DELETE SET NULL,
    purpose text NOT NULL,
    model_name text NOT NULL,
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    input_tokens integer CHECK (input_tokens IS NULL OR input_tokens >= 0),
    output_tokens integer CHECK (output_tokens IS NULL OR output_tokens >= 0),
    error_code text,
    error_message text,
    input_redacted jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_summary text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(input_redacted) = 'object')
);

CREATE INDEX model_calls_run_idx ON model_calls (agent_run_id, created_at DESC);
CREATE INDEX model_calls_session_idx ON model_calls (session_id, created_at DESC);

CREATE TABLE score_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    version integer NOT NULL DEFAULT 1,
    status report_status NOT NULL DEFAULT 'generating',
    overall_band numeric(2, 1) CHECK (overall_band IS NULL OR overall_band BETWEEN 0 AND 9),
    confidence numeric(4, 3) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    disclaimer text NOT NULL DEFAULT 'AI 模拟评分仅用于练习参考，不代表 IELTS 官方成绩。',
    model_run_id text REFERENCES agent_runs(id) ON DELETE SET NULL,
    raw_report jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, version),
    CHECK (jsonb_typeof(raw_report) = 'object')
);

CREATE INDEX score_reports_session_idx ON score_reports (session_id, created_at DESC);

CREATE TABLE criterion_scores (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL REFERENCES score_reports(id) ON DELETE CASCADE,
    criterion scoring_criterion NOT NULL,
    band numeric(2, 1) NOT NULL CHECK (band BETWEEN 0 AND 9),
    confidence numeric(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    suggestions jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_id, criterion),
    CHECK (jsonb_typeof(evidence) = 'array'),
    CHECK (jsonb_typeof(suggestions) = 'array'),
    CHECK (jsonb_typeof(raw_output) = 'object')
);

CREATE TABLE feedback_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL REFERENCES score_reports(id) ON DELETE CASCADE,
    category text NOT NULL,
    priority integer NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    title text NOT NULL,
    body text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(evidence_refs) = 'array')
);

CREATE TABLE reference_answers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL REFERENCES score_reports(id) ON DELETE CASCADE,
    turn_id uuid REFERENCES session_turns(id) ON DELETE SET NULL,
    band_target numeric(2, 1) CHECK (band_target IS NULL OR band_target BETWEEN 0 AND 9),
    skeleton jsonb NOT NULL DEFAULT '{}'::jsonb,
    answer_text text NOT NULL,
    personalization_notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (jsonb_typeof(skeleton) = 'object')
);

CREATE TABLE study_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid REFERENCES score_reports(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    priority integer NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    focus text NOT NULL,
    task text NOT NULL,
    due_on date,
    status text NOT NULL DEFAULT 'planned',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX study_plans_user_status_idx ON study_plans (user_id, status, created_at DESC);

CREATE TABLE prompt_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name text NOT NULL,
    purpose text NOT NULL,
    version text NOT NULL,
    content_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_name, purpose, version),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX prompt_versions_active_idx ON prompt_versions (agent_name, purpose) WHERE active = true;

CREATE TABLE eval_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_type text NOT NULL,
    dataset_name text NOT NULL,
    status text NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CHECK (jsonb_typeof(metrics) = 'object')
);

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER user_profiles_set_updated_at BEFORE UPDATE ON user_profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER background_questionnaires_set_updated_at BEFORE UPDATE ON background_questionnaires FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER background_facts_set_updated_at BEFORE UPDATE ON background_facts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER seasons_set_updated_at BEFORE UPDATE ON seasons FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER topic_categories_set_updated_at BEFORE UPDATE ON topic_categories FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER topics_set_updated_at BEFORE UPDATE ON topics FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER questions_set_updated_at BEFORE UPDATE ON questions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER cue_cards_set_updated_at BEFORE UPDATE ON cue_cards FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER followup_templates_set_updated_at BEFORE UPDATE ON followup_templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER knowledge_docs_set_updated_at BEFORE UPDATE ON knowledge_docs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER practice_sessions_set_updated_at BEFORE UPDATE ON practice_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER session_parts_set_updated_at BEFORE UPDATE ON session_parts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER session_turns_set_updated_at BEFORE UPDATE ON session_turns FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER score_reports_set_updated_at BEFORE UPDATE ON score_reports FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER study_plans_set_updated_at BEFORE UPDATE ON study_plans FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- +goose Down
DROP TABLE IF EXISTS eval_runs;
DROP TABLE IF EXISTS prompt_versions;
DROP TABLE IF EXISTS study_plans;
DROP TABLE IF EXISTS reference_answers;
DROP TABLE IF EXISTS feedback_items;
DROP TABLE IF EXISTS criterion_scores;
DROP TABLE IF EXISTS score_reports;
DROP TABLE IF EXISTS model_calls;
DROP TABLE IF EXISTS agent_steps;
ALTER TABLE IF EXISTS session_turns DROP CONSTRAINT IF EXISTS session_turns_agent_run_fk;
DROP TABLE IF EXISTS agent_runs;
DROP TABLE IF EXISTS speech_metrics;
DROP TABLE IF EXISTS asr_results;
DROP TABLE IF EXISTS audio_assets;
DROP TABLE IF EXISTS session_turns;
DROP TABLE IF EXISTS session_parts;
DROP TABLE IF EXISTS practice_sessions;
DROP TABLE IF EXISTS knowledge_chunks;
DROP TABLE IF EXISTS knowledge_docs;
DROP TABLE IF EXISTS question_versions;
DROP TABLE IF EXISTS followup_templates;
DROP TABLE IF EXISTS cue_cards;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS topics;
DROP TABLE IF EXISTS topic_categories;
DROP TABLE IF EXISTS seasons;
DROP TABLE IF EXISTS consent_records;
DROP TABLE IF EXISTS background_facts;
DROP TABLE IF EXISTS background_questionnaires;
DROP TABLE IF EXISTS user_profiles;
DROP TABLE IF EXISTS users;

DROP FUNCTION IF EXISTS set_updated_at();

DROP TYPE IF EXISTS knowledge_doc_type;
DROP TYPE IF EXISTS scoring_criterion;
DROP TYPE IF EXISTS report_status;
DROP TYPE IF EXISTS audio_kind;
DROP TYPE IF EXISTS turn_status;
DROP TYPE IF EXISTS session_status;
DROP TYPE IF EXISTS session_mode;
DROP TYPE IF EXISTS source_type;
DROP TYPE IF EXISTS content_status;
DROP TYPE IF EXISTS user_status;
DROP TYPE IF EXISTS user_role;

DROP EXTENSION IF EXISTS vector;
DROP EXTENSION IF EXISTS pgcrypto;
