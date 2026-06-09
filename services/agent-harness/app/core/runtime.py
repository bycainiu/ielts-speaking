from dataclasses import dataclass
from importlib import metadata, util


AGENT_FRAMEWORK_PACKAGE = "agent-framework-core"
AGENT_FRAMEWORK_IMPORT = "agent_framework"


@dataclass(frozen=True)
class AgentRuntime:
    name: str = "agent-runtime"
    framework: str = "deterministic-workflow"
    adapter: str = "microsoft-agent-framework"

    def describe(self) -> dict[str, str]:
        package_version = installed_package_version(AGENT_FRAMEWORK_PACKAGE)
        module_available = util.find_spec(AGENT_FRAMEWORK_IMPORT) is not None
        return {
            "name": self.name,
            "framework": self.framework,
            "adapter": self.adapter,
            "adapter_package": AGENT_FRAMEWORK_PACKAGE,
            "adapter_import": AGENT_FRAMEWORK_IMPORT,
            "adapter_installed": str(module_available or package_version is not None).lower(),
            "adapter_version": package_version or "not-installed",
            "mode": "deterministic",
            "note": "当前 API 使用确定性工作流保障回归稳定，运行时边界已按 Microsoft Agent Framework 适配方式暴露。",
        }


def installed_package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None
