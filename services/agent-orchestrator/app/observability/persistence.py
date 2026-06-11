from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.observability.db import load_psycopg
from app.observability.models import OrchestratorTraceSnapshot, ToolLoopIterationRecord
from app.protocols.agent_message import AgentMessage
from app.protocols.schemas import AgentStreamEvent


logger = logging.getLogger("agent_orchestrator.persistence")


class PostgresOrchestratorRepository:
    def __init__(self, database_url: str, *, reasoning_retention: str = "full") -> None:
        self.database_url = database_url
        self.reasoning_retention = reasoning_retention
        self.psycopg, self.Jsonb = load_psycopg()

    def save_run_observability(
        self,
        *,
        trace: OrchestratorTraceSnapshot,
        messages: list[AgentMessage],
        tool_iterations: list[ToolLoopIterationRecord],
        stream_events: list[AgentStreamEvent],
    ) -> None:
        session_uuid = _uuid_or_none(trace.session_id)
        with self._connect() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM agent_messages WHERE run_id = %s", (trace.run_id,))
                conn.execute("DELETE FROM tool_loop_iterations WHERE run_id = %s", (trace.run_id,))

                for message in messages:
                    conn.execute(
                        """
                        INSERT INTO agent_messages
                            (session_id, run_id, message_id, source_agent, target_agent,
                             message_type, payload, reply_to, context_snapshot, created_at)
                        VALUES
                            (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s)
                        ON CONFLICT (message_id) DO UPDATE SET
                            payload = EXCLUDED.payload,
                            reply_to = EXCLUDED.reply_to,
                            context_snapshot = EXCLUDED.context_snapshot
                        """,
                        (
                            session_uuid,
                            trace.run_id,
                            message.message_id,
                            message.source_agent,
                            message.target_agent,
                            message.message_type,
                            self._jsonb(message.payload),
                            message.reply_to,
                            self._jsonb(message.context.model_dump(mode="json")),
                            message.created_at,
                        ),
                    )

                for record in tool_iterations:
                    conn.execute(
                        """
                        INSERT INTO tool_loop_iterations
                            (session_id, run_id, agent_name, iteration, phase,
                             llm_request_messages, llm_response_content, llm_reasoning_text,
                             llm_tool_calls, tool_name, tool_arguments, tool_result, tool_status,
                             model_name, input_tokens, output_tokens, latency_ms, error_code, created_at)
                        VALUES
                            (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb,
                             %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            session_uuid,
                            trace.run_id,
                            record.agent_name,
                            record.iteration,
                            record.phase,
                            self._jsonb_or_none(record.llm_request_messages),
                            record.llm_response_content,
                            _apply_reasoning_retention(record.llm_reasoning_text, retention=self.reasoning_retention),
                            self._jsonb_or_none(record.llm_tool_calls),
                            record.tool_name,
                            self._jsonb_or_none(record.tool_arguments),
                            self._jsonb_or_none(record.tool_result),
                            record.tool_status,
                            record.model_name,
                            record.input_tokens,
                            record.output_tokens,
                            record.latency_ms,
                            record.error_code,
                            record.created_at,
                        ),
                    )

                conn.execute(
                    """
                    INSERT INTO agent_runs (id, session_id, status, metadata, started_at, finished_at,
                                            run_kind, subject_type, subject_id)
                    VALUES (%s, %s::uuid, %s, %s::jsonb, %s, %s, 'orchestrator_session', 'practice_session', %s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        metadata = EXCLUDED.metadata,
                        finished_at = EXCLUDED.finished_at
                    """,
                    (
                        trace.run_id,
                        session_uuid,
                        trace.status,
                        self._jsonb(
                            {
                                "orchestrator_trace": trace.model_dump(mode="json"),
                                "stream_event_count": len(stream_events),
                                "message_count": len(messages),
                                "tool_iteration_count": len(tool_iterations),
                            }
                        ),
                        trace.started_at,
                        trace.finished_at,
                        trace.session_id,
                    ),
                )

    def list_messages(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, source_agent, target_agent, message_type, payload,
                       reply_to, context_snapshot, created_at
                FROM agent_messages
                WHERE run_id = %s
                ORDER BY created_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_tool_iterations(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT agent_name, iteration, phase, llm_request_messages, llm_response_content,
                       llm_reasoning_text, llm_tool_calls, tool_name, tool_arguments, tool_result,
                       tool_status, model_name, input_tokens, output_tokens, latency_ms, error_code, created_at
                FROM tool_loop_iterations
                WHERE run_id = %s
                ORDER BY created_at ASC, iteration ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> Any:
        return self.psycopg.connect(self.database_url, row_factory=self.psycopg.rows.dict_row)

    def _jsonb(self, value: Any) -> Any:
        return self.Jsonb(value)

    def _jsonb_or_none(self, value: Any) -> Any:
        return None if value is None else self.Jsonb(value)


def _uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        return str(uuid5(NAMESPACE_URL, f"orchestrator-session:{value}"))


def _apply_reasoning_retention(text: str | None, *, retention: str = "full") -> str | None:
    if not text or retention == "full":
        return text
    if retention == "none":
        return None
    if len(text) <= 400:
        return text
    return f"{text[:200]}…{text[-200:]}"
