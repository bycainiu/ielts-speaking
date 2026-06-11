from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from app.llm.gateway import LlmGateway
from app.llm.types import AgentToolLoopResult, LlmToolResponse
from app.observability.trace import OrchestratorTraceRecorder
from app.protocols.agent_message import SessionContext
from app.safety.guardrail import GuardrailAgent
from app.tools.registry import ToolRegistry


logger = logging.getLogger("agent_orchestrator.tool_loop")


class AgentToolLoop:
    def __init__(
        self,
        gateway: LlmGateway,
        tool_registry: ToolRegistry,
        guardrail: GuardrailAgent,
        trace_recorder: OrchestratorTraceRecorder | None = None,
        max_iterations: int = 5,
    ) -> None:
        self._gateway = gateway
        self._registry = tool_registry
        self._guardrail = guardrail
        self._trace = trace_recorder
        self._max_iterations = max(1, max_iterations)

    async def run(
        self,
        *,
        run_id: str,
        agent_name: str,
        task: str,
        system_prompt: str,
        user_message: str,
        tools: list[str],
        context: SessionContext,
        mock_responses: list[LlmToolResponse] | None = None,
    ) -> AgentToolLoopResult | None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        tool_schemas = self._registry.schemas_for(tools)
        tool_calls_made: list[str] = []
        reasoning_parts: list[str] = []

        for iteration in range(self._max_iterations):
            self._publish_thinking(run_id, context, agent_name, iteration, "Analyzing task...")
            response = await self._next_response(
                task=task,
                messages=messages,
                tool_schemas=tool_schemas,
                mock_responses=mock_responses,
                iteration=iteration,
            )
            if response is None:
                return None

            if response.reasoning_text:
                reasoning_parts.append(response.reasoning_text)
                self._publish_thinking(run_id, context, agent_name, iteration, response.reasoning_text)

            self._record_llm_iteration(run_id, context, agent_name, iteration, messages, response)

            if not response.tool_calls:
                parsed = _parse_json_content(response.content)
                return AgentToolLoopResult(
                    output=parsed if parsed is not None else response.content,
                    iterations=iteration + 1,
                    fallback_used=False,
                    tool_calls_made=tool_calls_made,
                    reasoning_text="\n".join(reasoning_parts) or None,
                )

            assistant_tool_calls = []
            for call in response.tool_calls:
                guard = self._guardrail.evaluate_tool_request(
                    tool_name=call.name,
                    allowed_tool_names=tools,
                    arguments=call.arguments,
                    user_text=user_message,
                )
                if not guard.allowed:
                    self._record_guardrail_block(run_id, context, agent_name, iteration, call.name)
                    continue

                self._publish_tool_call(run_id, context, agent_name, call.name, call.arguments)
                tool_result = await self._registry.execute(call.name, call.arguments, context)
                tool_calls_made.append(call.name)
                self._publish_tool_result(run_id, context, agent_name, call.name, tool_result.output, tool_result.latency_ms)
                self._record_tool_iteration(run_id, context, agent_name, iteration, call, tool_result)
                assistant_tool_calls.append(
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(tool_result.output, ensure_ascii=False),
                    }
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": assistant_tool_calls,
                }
            )

        logger.warning("tool_loop_max_iterations", extra={"agent": agent_name, "run_id": run_id})
        return None

    async def _next_response(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        mock_responses: list[LlmToolResponse] | None,
        iteration: int,
    ) -> LlmToolResponse | None:
        if mock_responses and iteration < len(mock_responses):
            return mock_responses[iteration]
        return await self._gateway.complete_with_tools(
            task=task,
            messages=messages,
            tools=tool_schemas,
        )

    def _publish_thinking(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        iteration: int,
        delta: str,
    ) -> None:
        if self._trace is None:
            return
        self._trace.stream_broker.publish(
            run_id=run_id,
            session_id=context.session_id,
            kind="agent.thinking",
            phase=agent_name,
            reasoning_delta=delta,
            payload={"agent_name": agent_name, "iteration": iteration},
        )

    def _publish_tool_call(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        if self._trace is None:
            return
        self._trace.stream_broker.publish(
            run_id=run_id,
            session_id=context.session_id,
            kind="agent.tool_call",
            phase=agent_name,
            payload={"tool": tool_name, "arguments": arguments},
        )

    def _publish_tool_result(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        tool_name: str,
        result: dict[str, Any],
        latency_ms: int,
    ) -> None:
        if self._trace is None:
            return
        self._trace.stream_broker.publish(
            run_id=run_id,
            session_id=context.session_id,
            kind="agent.tool_result",
            phase=agent_name,
            payload={"tool": tool_name, "result": result, "latency_ms": latency_ms},
        )

    def _record_llm_iteration(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        iteration: int,
        messages: list[dict[str, Any]],
        response: LlmToolResponse,
    ) -> None:
        if self._trace is None:
            return
        self._trace.record_tool_loop_iteration(
            session_id=context.session_id,
            run_id=run_id,
            agent_name=agent_name,
            iteration=iteration,
            phase="llm_call",
            llm_request_messages=messages,
            llm_response_content=response.content,
            llm_reasoning_text=response.reasoning_text,
            llm_tool_calls=[{"name": c.name, "arguments": c.arguments} for c in response.tool_calls],
            model_name=response.model_name,
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
        )

    def _record_tool_iteration(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        iteration: int,
        call: Any,
        tool_result: Any,
    ) -> None:
        if self._trace is None:
            return
        self._trace.record_tool_loop_iteration(
            session_id=context.session_id,
            run_id=run_id,
            agent_name=agent_name,
            iteration=iteration,
            phase="tool_execute",
            tool_name=call.name,
            tool_arguments=call.arguments,
            tool_result=tool_result.output,
            tool_status=tool_result.status,
            latency_ms=tool_result.latency_ms,
        )

    def _record_guardrail_block(
        self,
        run_id: str,
        context: SessionContext,
        agent_name: str,
        iteration: int,
        tool_name: str,
    ) -> None:
        if self._trace is None:
            return
        self._trace.record_tool_loop_iteration(
            session_id=context.session_id,
            run_id=run_id,
            agent_name=agent_name,
            iteration=iteration,
            phase="guardrail_check",
            tool_name=tool_name,
            tool_status="guardrail_blocked",
        )


def _parse_json_content(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
