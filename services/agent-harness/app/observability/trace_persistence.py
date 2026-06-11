from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.observability.langfuse_client import AgentRunTrace, TraceLlmCall, is_real_llm_call, sanitize_raw_payload, sanitize_text
from app.protocols.schemas import SessionEvent
from app.rag.llamaindex_service import load_psycopg


logger = logging.getLogger("agent_harness.trace_persistence")

SESSION_MODES = {"full_exam", "part_practice", "topic_practice"}


class PostgresTraceRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.psycopg, self.Jsonb = load_psycopg()

    def save_trace(self, trace: AgentRunTrace, *, events: Sequence[SessionEvent] | None = None) -> None:
        trace_payload = trace.model_dump(mode="json", exclude_none=True)
        metadata = {
            "trace_schema_version": "agent_run_trace.v2",
            "trace_payload": trace_payload,
            "user_id_hash": trace.user_id_hash,
            "part": trace.part,
            "question_id": trace.question_id,
            "step_count": len(trace.steps),
            "llm_call_count": sum(1 for step in trace.steps for call in step.llm_calls),
            "captured_llm_call_count": sum(1 for step in trace.steps for call in step.llm_calls if is_real_llm_call(call)),
            "tool_call_count": sum(len(step.tool_calls) for step in trace.steps),
            "stream_event_count": len(trace.stream_events),
            "reasoning_block_count": sum(len(step.reasoning_blocks) for step in trace.steps),
        }
        session_uuid = uuid_or_none(trace.session_id)
        mode = trace.mode if trace.mode in SESSION_MODES else None

        with self._connect() as conn:
            with conn.transaction():
                conn.execute("delete from model_calls where agent_run_id = %s", (trace.run_id,))
                conn.execute("delete from agent_run_events where run_id = %s", (trace.run_id,))
                conn.execute("delete from agent_steps where run_id = %s", (trace.run_id,))
                conn.execute(
                    """
                    insert into agent_runs
                        (id, session_id, user_id, mode, status, metadata, started_at, finished_at,
                         run_kind, subject_type, subject_id)
                    values
                        (%s, %s::uuid, null, %s::session_mode, %s, %s::jsonb, %s, %s,
                         'session_workflow', 'practice_session', %s)
                    on conflict (id) do update set
                        session_id = excluded.session_id,
                        mode = excluded.mode,
                        status = excluded.status,
                        metadata = excluded.metadata,
                        started_at = excluded.started_at,
                        finished_at = excluded.finished_at,
                        run_kind = excluded.run_kind,
                        subject_type = excluded.subject_type,
                        subject_id = excluded.subject_id
                    """,
                    (
                        trace.run_id,
                        session_uuid,
                        mode,
                        trace.status,
                        self._jsonb(metadata),
                        trace.started_at,
                        trace.finished_at,
                        trace.session_id,
                    ),
                )

                step_ids: dict[str, str] = {}
                for step in trace.steps:
                    row = conn.execute(
                        """
                        insert into agent_steps
                            (run_id, workflow_node, agent_name, prompt_version, model_name, execution_kind,
                             status, input_summary, output_summary, latency_ms, error_code, started_at, finished_at,
                             part, question_id, input_payload, input_detail, output_payload, messages,
                             retrieved_chunks, structured_output_validity, scoring_result, error_type,
                             input_tokens, output_tokens, estimated_cost_usd)
                        values
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                             %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                             %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s)
                        returning id::text
                        """,
                        (
                            trace.run_id,
                            step.workflow_node,
                            step.agent_name,
                            step.prompt_version,
                            step.model_name,
                            step.execution_kind,
                            step.status,
                            step.input_summary,
                            step.output_summary,
                            step.latency_ms,
                            step.error_code,
                            step.started_at,
                            step.finished_at,
                            step.part,
                            step.question_id,
                            self._jsonb_or_none(step.input_payload),
                            self._jsonb_or_none(step.input_detail),
                            self._jsonb_or_none(step.output_payload),
                            self._jsonb_or_none([message.model_dump(mode="json", exclude_none=True) for message in step.messages] if step.messages else None),
                            self._jsonb_or_none(step.retrieved_chunks),
                            step.structured_output_validity,
                            self._jsonb_or_none(step.scoring_result),
                            step.error_type,
                            step.input_tokens,
                            step.output_tokens,
                            step.estimated_cost_usd,
                        ),
                    ).fetchone()
                    step_ids[step.step_id] = row["id"]
                    for call in step.llm_calls:
                        if is_real_llm_call(call):
                            self._insert_model_call(conn, trace, call, step_ids[step.step_id])

                for index, event in enumerate(events or []):
                    conn.execute(
                        """
                        insert into agent_run_events
                            (run_id, step_id, event_index, event_type, title, summary, visibility, payload, created_at)
                        values
                            (%s, null, %s, %s, %s, %s, 'default', %s::jsonb, %s)
                        on conflict (run_id, event_index) do update set
                            event_type = excluded.event_type,
                            title = excluded.title,
                            summary = excluded.summary,
                            payload = excluded.payload,
                            created_at = excluded.created_at
                        """,
                        (
                            trace.run_id,
                            index,
                            event.type,
                            event.type,
                            summarize_json(event.payload),
                            self._jsonb(sanitize_raw_payload(event.payload)),
                            event.created_at,
                        ),
                    )

    def get_trace(self, run_id: str) -> AgentRunTrace | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                select metadata -> 'trace_payload' as trace_payload
                from agent_runs
                where id = %s
                  and metadata ? 'trace_payload'
                """,
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return trace_from_payload(row["trace_payload"])

    def list_runs(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
        limit: int = 100,
    ) -> list[AgentRunTrace]:
        conditions = ["metadata ? 'trace_payload'"]
        params: list[Any] = []
        if run_id:
            conditions.append("id = %s")
            params.append(run_id)
        if session_id:
            conditions.append("metadata -> 'trace_payload' ->> 'session_id' = %s")
            params.append(session_id)
        if mode:
            conditions.append("metadata -> 'trace_payload' ->> 'mode' = %s")
            params.append(mode)
        params.append(max(1, limit))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select metadata -> 'trace_payload' as trace_payload
                from agent_runs
                where {' and '.join(conditions)}
                order by started_at desc
                limit %s
                """,
                tuple(params),
            ).fetchall()
        traces = [trace_from_payload(row["trace_payload"]) for row in rows]
        return [trace for trace in traces if trace is not None]

    def session_ids(self, *, limit: int = 100) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select metadata -> 'trace_payload' ->> 'session_id' as session_id,
                       max(started_at) as last_started_at
                from agent_runs
                where metadata ? 'trace_payload'
                group by metadata -> 'trace_payload' ->> 'session_id'
                order by last_started_at desc
                limit %s
                """,
                (max(1, limit),),
            ).fetchall()
        return [row["session_id"] for row in rows if row["session_id"]]

    def list_events(self, session_id: str, *, limit: int = 500) -> list[SessionEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select
                    e.event_type,
                    ar.metadata -> 'trace_payload' ->> 'session_id' as session_id,
                    e.run_id,
                    e.payload,
                    e.created_at
                from agent_run_events e
                join agent_runs ar on ar.id = e.run_id
                where ar.metadata ? 'trace_payload'
                  and ar.metadata -> 'trace_payload' ->> 'session_id' = %s
                order by e.created_at asc, e.event_index asc
                limit %s
                """,
                (session_id, max(1, limit)),
            ).fetchall()
        events: list[SessionEvent] = []
        for row in rows:
            try:
                events.append(
                    SessionEvent(
                        type=row["event_type"],
                        session_id=row["session_id"] or session_id,
                        run_id=row["run_id"],
                        payload=row["payload"] or {},
                        created_at=row["created_at"],
                    )
                )
            except Exception as exc:
                logger.warning("skip_invalid_persisted_trace_event", extra={"run_id": row.get("run_id"), "error": str(exc)})
        return events[-max(1, limit) :]

    def mark_cancelled(self, run_id: str) -> AgentRunTrace | None:
        trace = self.get_trace(run_id)
        if trace is None:
            return None
        updated = trace.model_copy(update={"status": "cancelled", "finished_at": datetime.now(UTC)})
        trace_payload = updated.model_dump(mode="json", exclude_none=True)
        with self._connect() as conn:
            conn.execute(
                """
                update agent_runs
                set status = 'cancelled',
                    finished_at = %s,
                    metadata = jsonb_set(metadata, '{trace_payload}', %s::jsonb, true)
                where id = %s
                """,
                (updated.finished_at, self._jsonb(trace_payload), run_id),
            )
        return updated

    def _insert_model_call(self, conn: Any, trace: AgentRunTrace, call: TraceLlmCall, step_id: str) -> None:
        input_redacted = {
            "llm_call_id": call.llm_call_id,
            "provider": call.provider,
            "input_summary": call.input_summary,
            "request_payload": call.request_payload,
        }
        output_payload = {
            "llm_call_id": call.llm_call_id,
            "provider": call.provider,
            "response_payload": call.response_payload,
        }
        conn.execute(
            """
            insert into model_calls
                (session_id, user_id, agent_run_id, purpose, model_name, latency_ms,
                 input_tokens, output_tokens, error_code, error_message, input_redacted,
                 output_summary, created_at, step_id, call_name, agent_name, execution_kind,
                 payload_origin, prompt_version, status, request_payload, response_payload)
            values
                (%s::uuid, null, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                 %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                uuid_or_none(trace.session_id),
                trace.run_id,
                call.call_name,
                call.model_name or "model-call",
                call.latency_ms,
                call.input_tokens,
                call.output_tokens,
                call.error_code,
                call.error_code,
                self._jsonb(sanitize_raw_payload(input_redacted)),
                call.output_summary,
                call.started_at,
                step_id,
                call.call_name,
                call.agent_name,
                call.execution_kind,
                call.payload_origin,
                call.prompt_version,
                call.status,
                self._jsonb_or_none(call.request_payload),
                self._jsonb_or_none(output_payload),
            ),
        )

    def _connect(self) -> Any:
        return self.psycopg.connect(self.database_url, row_factory=self.psycopg.rows.dict_row)

    def _jsonb(self, value: Any) -> Any:
        return self.Jsonb(value)

    def _jsonb_or_none(self, value: Any) -> Any:
        return None if value is None else self.Jsonb(value)


def trace_from_payload(payload: Any) -> AgentRunTrace | None:
    if not isinstance(payload, dict):
        return None
    try:
        return AgentRunTrace.model_validate(payload)
    except Exception as exc:
        logger.warning("skip_invalid_persisted_trace", extra={"error": str(exc)})
        return None


def uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        return None


def summarize_json(value: Any, *, limit: int = 220) -> str | None:
    try:
        text = json.dumps(sanitize_raw_payload(value), ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    return sanitize_text(text, limit=limit)
