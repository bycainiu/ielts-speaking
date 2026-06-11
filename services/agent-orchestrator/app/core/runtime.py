from dataclasses import dataclass


@dataclass(frozen=True)
class OrchestratorRuntime:
    name: str = "agent-orchestrator"
    framework: str = "multi-agent-orchestration"
    adapter: str = "exam-director"

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "framework": self.framework,
            "adapter": self.adapter,
            "mode": "multi-agent",
            "note": "ExamDirector 规则编排 + Specialist Agent LLM tool calling。",
        }
