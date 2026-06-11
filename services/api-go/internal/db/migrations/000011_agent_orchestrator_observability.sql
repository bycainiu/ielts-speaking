-- +goose Up
CREATE TABLE IF NOT EXISTS agent_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    run_id          TEXT NOT NULL,
    message_id      TEXT NOT NULL UNIQUE,
    source_agent    TEXT NOT NULL,
    target_agent    TEXT NOT NULL,
    message_type    TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    reply_to        TEXT,
    context_snapshot JSONB,
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_run ON agent_messages(run_id);

CREATE TABLE IF NOT EXISTS tool_loop_iterations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    run_id          TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    iteration       INT NOT NULL,
    phase           TEXT NOT NULL,
    llm_request_messages JSONB,
    llm_response_content TEXT,
    llm_reasoning_text   TEXT,
    llm_tool_calls       JSONB,
    tool_name        TEXT,
    tool_arguments   JSONB,
    tool_result      JSONB,
    tool_status      TEXT,
    model_name       TEXT,
    input_tokens     INT,
    output_tokens    INT,
    latency_ms       INT,
    error_code       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_loop_session ON tool_loop_iterations(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_loop_run ON tool_loop_iterations(run_id);

-- +goose Down
DROP INDEX IF EXISTS idx_tool_loop_run;
DROP INDEX IF EXISTS idx_tool_loop_session;
DROP TABLE IF EXISTS tool_loop_iterations;
DROP INDEX IF EXISTS idx_agent_messages_run;
DROP INDEX IF EXISTS idx_agent_messages_session;
DROP TABLE IF EXISTS agent_messages;
