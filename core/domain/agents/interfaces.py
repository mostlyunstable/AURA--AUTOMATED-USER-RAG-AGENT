from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from core.domain.agents.entities import Agent, AgentRun, ToolCall
from core.domain.agents.enums import AgentCapability


class AgentRepository(Protocol):
    async def create(self, agent: Agent) -> None: ...

    async def get(self, agent_id: UUID) -> Optional[Agent]: ...

    async def get_by_type(self, agent_type: str) -> List[Agent]: ...


class AgentRunRepository(Protocol):
    async def create(self, run: AgentRun) -> None: ...

    async def get(self, run_id: UUID) -> Optional[AgentRun]: ...

    async def get_by_task_execution(
        self, task_execution_id: UUID
    ) -> List[AgentRun]: ...

    async def update(self, run: AgentRun) -> None: ...


class ToolCallRepository(Protocol):
    async def create(self, call: ToolCall) -> None: ...

    async def get(self, call_id: UUID) -> Optional[ToolCall]: ...

    async def get_by_agent_run(self, agent_run_id: UUID) -> List[ToolCall]: ...

    async def update(self, call: ToolCall) -> None: ...


class PolicyRepository(Protocol):
    async def get_effective_policy(
        self, mission_id: UUID, agent_id: UUID
    ) -> "AgentPolicy": ...


class AgentPolicy:
    def __init__(
        self,
        allowed_capabilities: List[AgentCapability],
        denied_capabilities: List[AgentCapability],
        max_iterations: int = 50,
        max_tool_calls: int = 100,
        max_runtime_seconds: int = 1800,
        max_failed_actions: int = 5,
        requires_approval_for: Optional[List[str]] = None,
    ):
        self.allowed_capabilities = set(allowed_capabilities)
        self.denied_capabilities = set(denied_capabilities)
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.max_runtime_seconds = max_runtime_seconds
        self.max_failed_actions = max_failed_actions
        self.requires_approval_for = requires_approval_for or []

    def is_allowed(self, capability: AgentCapability) -> bool:
        if capability in self.denied_capabilities:
            return False
        if capability in self.allowed_capabilities:
            return True
        return False

    def check_limits(self, run: AgentRun) -> Optional[str]:
        if run.iteration_count >= self.max_iterations:
            return f"Iteration limit exceeded: {run.iteration_count} >= {self.max_iterations}"
        if run.tool_call_count >= self.max_tool_calls:
            return f"Tool call limit exceeded: {run.tool_call_count} >= {self.max_tool_calls}"
        return None


class ToolGateway(Protocol):
    async def execute_tool(
        self,
        agent_run: AgentRun,
        tool_name: str,
        arguments: Dict[str, Any],
        worktree_path: str,
    ) -> "ToolResult": ...


class ToolResult:
    def __init__(
        self,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.output = output
        self.error = error
        self.metadata = metadata or {}


class AgentRuntime(Protocol):
    async def run(
        self,
        task_id: UUID,
        task_execution_id: UUID,
        agent_id: UUID,
        worktree_path: str,
        repository_id: str,
    ) -> AgentRun: ...
