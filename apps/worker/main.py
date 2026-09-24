"""AURA Worker CLI - Entry point for running worker processes."""

import asyncio
import os
import signal
import sys
from typing import Any, Dict
from uuid import UUID

import click
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.application.agent_runtime import CodingAgentRuntime
from core.application.execution_service import ExecutionService
from core.application.tool_gateway import ToolGateway as ToolGatewayImpl
from core.application.verification_engine import VerificationEngine
from core.application.worker_coordinator import WorkerCoordinator
from core.domain.agents.entities import Agent
from core.domain.agents.enums import AgentCapability, AgentStatus, AgentType
from core.domain.agents.interfaces import AgentPolicy, ToolGateway
from core.domain.llm.interfaces import LLMProvider
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork
from core.infrastructure.execution.git_worktree import LocalGitWorktreeManager
from core.infrastructure.execution.local_sandbox import LocalSandboxManager
from core.infrastructure.llm.fake_provider import FakeLLMProvider
from core.infrastructure.llm.nvidia_provider import NvidiaLLMProvider


def get_llm_provider() -> LLMProvider:
    """Create LLM provider based on environment."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if api_key:
        return NvidiaLLMProvider(api_key=api_key)
    return FakeLLMProvider()


def get_worktree_root() -> str:
    """Get worktree root from environment or default."""
    return os.getenv("AURA_WORKTREE_ROOT", "~/.aura/worktrees")


def get_worker_name() -> str:
    """Get worker name from environment or generate."""
    return os.getenv("AURA_WORKER_NAME", f"aura-worker-{os.getpid()}")


def get_worker_capabilities() -> list[str]:
    """Get worker capabilities from environment."""
    caps = os.getenv("AURA_WORKER_CAPABILITIES")
    if caps:
        return [c.strip() for c in caps.split(",")]
    return ["CODING", "TESTING"]


def get_poll_interval() -> float:
    """Get poll interval from environment."""
    return float(os.getenv("AURA_WORKER_POLL_INTERVAL", "5.0"))


def get_lease_ttl() -> int:
    """Get lease TTL from environment."""
    return int(os.getenv("AURA_WORKER_LEASE_TTL", "90"))


def get_heartbeat_interval() -> int:
    """Get heartbeat interval from environment."""
    return int(os.getenv("AURA_WORKER_HEARTBEAT_INTERVAL", "30"))


def get_shutdown_timeout() -> int:
    """Get shutdown timeout from environment."""
    return int(os.getenv("AURA_WORKER_SHUTDOWN_TIMEOUT", "30"))


async def create_worker_services(uow_factory) -> Dict[str, Any]:
    """Create the service factories for the worker coordinator."""
    llm_provider = get_llm_provider()
    worktree_manager = LocalGitWorktreeManager(worktree_root=get_worktree_root())
    sandbox_manager = LocalSandboxManager()

    # Create a default agent
    agent = Agent(
        name="aura-coding-agent",
        agent_type=AgentType.CODING_AGENT,
        version="1.0.0",
        capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
            AgentCapability.SEARCH_REPOSITORY,
            AgentCapability.RUN_TESTS,
            AgentCapability.RUN_COMMAND,
            AgentCapability.READ_GIT,
            AgentCapability.WRITE_GIT,
            AgentCapability.FINISH_TASK,
        ],
        status=AgentStatus.ACTIVE,
    )

    # Agent policy - allow all capabilities by default
    agent_policy = AgentPolicy(
        allowed_capabilities=[
            AgentCapability.READ_REPOSITORY,
            AgentCapability.WRITE_REPOSITORY,
            AgentCapability.SEARCH_REPOSITORY,
            AgentCapability.RUN_TESTS,
            AgentCapability.RUN_COMMAND,
            AgentCapability.READ_GIT,
            AgentCapability.WRITE_GIT,
            AgentCapability.FINISH_TASK,
        ],
        denied_capabilities=[],
        max_iterations=50,
        max_tool_calls=100,
        max_runtime_seconds=1800,
        max_failed_actions=5,
    )

    def tool_gateway_factory(uow):
        """Create ToolGateway with the execution service."""
        execution_service = ExecutionService(
            uow=uow,
            worktree_manager=worktree_manager,
            sandbox_manager=sandbox_manager,
        )
        return ToolGatewayImpl(
            uow=uow,
            execution_service=execution_service,
        )

    def agent_runtime_factory(uow):
        """Create CodingAgent with all dependencies."""
        tool_gateway = tool_gateway_factory(uow)
        return CodingAgentRuntime(
            uow=uow,
            llm_provider=llm_provider,
            tool_gateway=tool_gateway,
            agent_policy=agent_policy,
            agent=agent,
        )

    def execution_service_factory(uow):
        """Create ExecutionService with the UoW."""
        return ExecutionService(
            uow=uow,
            worktree_manager=worktree_manager,
            sandbox_manager=sandbox_manager,
        )

    def verification_factory(uow):
        """Create VerificationEngine with the UoW."""
        return VerificationEngine(uow)

    return {
        "agent": agent,
        "llm_provider": llm_provider,
        "agent_policy": agent_policy,
        "tool_gateway_factory": tool_gateway_factory,
        "agent_runtime_factory": agent_runtime_factory,
        "execution_service_factory": execution_service_factory,
        "verification_factory": verification_factory,
    }


async def run_worker(
    mission_id: str,
    uow_factory,
    worker_name: str,
    capabilities: list[str],
    poll_interval: float,
    lease_ttl: int,
    heartbeat_interval: int,
    shutdown_timeout: int,
    services: dict,
):
    """Run a single worker coordinator."""
    coordinator = WorkerCoordinator(
        uow_factory=uow_factory,
        mission_id=UUID(mission_id),
        agent=services["agent"],
        execution_service_factory=services["execution_service_factory"],
        agent_runtime_factory=services["agent_runtime_factory"],
        verification_factory=services["verification_factory"],
        worker_name=worker_name,
        capabilities=capabilities,
        poll_interval_seconds=poll_interval,
        lease_ttl_seconds=lease_ttl,
        heartbeat_interval_seconds=heartbeat_interval,
        shutdown_timeout_seconds=shutdown_timeout,
    )

    # Handle signals for graceful shutdown
    def signal_handler():
        print(f"[{worker_name}] Received shutdown signal, draining...")
        asyncio.create_task(coordinator.shutdown(graceful=True))

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    print(f"[{worker_name}] Starting worker for mission {mission_id}")
    print(f"[{worker_name}] Capabilities: {capabilities}")
    print(f"[{worker_name}] Poll interval: {poll_interval}s")
    print(f"[{worker_name}] Lease TTL: {lease_ttl}s")
    print(f"[{worker_name}] Heartbeat interval: {heartbeat_interval}s")

    try:
        await coordinator.run_forever()
    except asyncio.CancelledError:
        print(f"[{worker_name}] Cancelled")
    except Exception as e:
        print(f"[{worker_name}] Error: {e}")
        raise
    finally:
        await coordinator.shutdown(graceful=True)
        print(f"[{worker_name}] Stopped")


@click.command()
@click.option("--mission-id", required=True, help="Mission ID to work on")
@click.option(
    "--worker-name", default=None, help="Worker name (default: auto-generated)"
)
@click.option("--capabilities", default=None, help="Comma-separated capabilities")
@click.option(
    "--poll-interval", default=None, type=float, help="Poll interval in seconds"
)
@click.option("--lease-ttl", default=None, type=int, help="Lease TTL in seconds")
@click.option(
    "--heartbeat-interval", default=None, type=int, help="Heartbeat interval in seconds"
)
@click.option(
    "--shutdown-timeout", default=None, type=int, help="Shutdown timeout in seconds"
)
@click.option("--count", default=1, type=int, help="Number of workers to run")
def main(
    mission_id: str,
    worker_name: str,
    capabilities: str,
    poll_interval: float,
    lease_ttl: int,
    heartbeat_interval: int,
    shutdown_timeout: int,
    count: int,
):
    """Run AURA worker(s) for a mission."""
    # Validate mission_id
    try:
        UUID(mission_id)
    except ValueError:
        click.echo(f"Invalid mission ID: {mission_id}", err=True)
        sys.exit(1)

    # Database setup
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        click.echo("DATABASE_URL environment variable is required", err=True)
        sys.exit(1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def uow_factory():
        return SQLAlchemyUnitOfWork(session_factory)

    # Resolve configuration
    resolved_worker_name = worker_name or get_worker_name()
    resolved_capabilities = (
        [c.strip() for c in capabilities.split(",")]
        if capabilities
        else get_worker_capabilities()
    )
    resolved_poll_interval = poll_interval or get_poll_interval()
    resolved_lease_ttl = lease_ttl or get_lease_ttl()
    resolved_heartbeat_interval = heartbeat_interval or get_heartbeat_interval()
    resolved_shutdown_timeout = shutdown_timeout or get_shutdown_timeout()

    # Create shared services
    services = asyncio.run(create_worker_services(uow_factory))

    if count == 1:
        # Single worker
        asyncio.run(
            run_worker(
                mission_id=mission_id,
                uow_factory=uow_factory,
                worker_name=resolved_worker_name,
                capabilities=resolved_capabilities,
                poll_interval=resolved_poll_interval,
                lease_ttl=resolved_lease_ttl,
                heartbeat_interval=resolved_heartbeat_interval,
                shutdown_timeout=resolved_shutdown_timeout,
                services=services,
            )
        )
    else:
        # Multiple workers - run concurrently
        async def run_multiple():
            tasks = []
            for i in range(count):
                name = f"{resolved_worker_name}-{i}"
                task = run_worker(
                    mission_id=mission_id,
                    uow_factory=uow_factory,
                    worker_name=name,
                    capabilities=resolved_capabilities,
                    poll_interval=resolved_poll_interval,
                    lease_ttl=resolved_lease_ttl,
                    heartbeat_interval=resolved_heartbeat_interval,
                    shutdown_timeout=resolved_shutdown_timeout,
                    services=services,
                )
                tasks.append(task)
            await asyncio.gather(*tasks)

        asyncio.run(run_multiple())


if __name__ == "__main__":
    main()
