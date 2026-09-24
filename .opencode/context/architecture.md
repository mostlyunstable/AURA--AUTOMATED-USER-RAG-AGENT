# AURA Architecture

**LAST VERIFIED: 2026-09-21 / d383203 (AURA-008)**

## System Overview

AURA is an autonomous engineering platform organized as a clean architecture with three layers:

```
Domain (pure Python, no external deps)
    ↓
Application (orchestration, no framework)
    ↓
Infrastructure (SQLAlchemy, FastAPI, LLM, etc.)
```

---

## Subsystems

### Domain Layer (`core/domain/`)

Pure domain models, enums, state machines, and entities. Zero external dependencies.

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `agents/` | Agent entities, capabilities, runs, tool calls, verification | `Agent`, `AgentRun`, `AgentPolicy`, `VerificationResult` |
| `approvals/` | Approval workflow entities | `Approval`, `ApprovalStatus` |
| `context/` | Task/agent context for execution | `TaskContext` |
| `dag/` | Task dependency graph | `TaskDependency` |
| `events/` | Domain events | `Event` |
| `execution/` | Execution environment, commands, artifacts | `ExecutionEnvironment`, `ExecutionCommand`, `Artifact` |
| `llm/` | LLM provider interfaces | `LLMProvider`, `LLMRequest`, `LLMResponse` |
| `missions/` | Mission entity, status, risk | `Mission`, `MissionStatus` |
| `plans/` | Engineering plans | `EngineeringPlan`, `PlannerOutput` |
| `policies/` | Policy definitions | `Policy` |
| `pull_requests/` | PR entities | `PullRequest`, `PullRequestStatus` |
| `tasks/` | Task entity, types, status, execution | `Task`, `TaskExecution`, `TaskStatus`, `TaskType` |
| `workers/` | Worker, lease, heartbeat entities | `Worker`, `TaskLease`, `WorkerHeartbeat` |

### Application Layer (`core/application/`)

Orchestration services. Depends only on Domain + interfaces.

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `worker_coordinator.py` | **Main worker orchestration** - registration, claim, lease, heartbeat, execute, verify, complete, recover | `WorkerCoordinator` |
| `task_scheduler.py` | Atomic task state transitions (PENDING→READY→QUEUED) with dependency resolution | `TaskScheduler` |
| `agent_runtime.py` | Base agent runtime | `CodingAgentRuntime` |
| `coding_agent.py` | Concrete coding agent with tool use + verification | `CodingAgent` |
| `planner_agent.py` | Planning agent | `PlannerAgent` |
| `mission_service.py` | Mission lifecycle, approvals | `MissionService` |
| `mission_orchestrator.py` | High-level mission flow | `MissionOrchestrator` |
| `execution_service.py` | Environment + sandbox + worktree | `ExecutionService` |
| `tool_gateway.py` | Tool execution with policy + worktree containment | `ToolGateway` |
| `verification_engine.py` | Independent verification (git, tests, scope, secrets) | `VerificationEngine` |
| `verification_engine.py` | Orphan environment recovery | `OrphanRecoveryService` |
| `interfaces.py` | Repository interfaces (UnitOfWork pattern) | `UnitOfWork`, `TaskRepository`, `WorkerRepository`, etc. |

### Infrastructure Layer (`core/infrastructure/`)

External adapters. Implements application interfaces.

| Module | Responsibility | Key Classes |
|--------|---------------|-------------|
| `database/` | SQLAlchemy async models, repositories, UnitOfWork | `SQLAlchemyUnitOfWork`, `SQLAlchemy*Repository` |
| `execution/` | Local sandbox, git worktree, artifact collector, path containment | `LocalSandboxManager`, `LocalGitWorktreeManager`, `ArtifactCollector` |
| `llm/` | LLM providers (NVIDIA, fake) | `NvidiaLLMProvider`, `FakeLLMProvider` |
| `logging/` | Structured logging | `setup_logging` |
| `metrics/` | Prometheus metrics | `aura_*` counters/histograms |

### API Layer (`apps/`)

| App | Responsibility |
|-----|---------------|
| `api/` | FastAPI HTTP endpoints (missions, tasks, executions, PRs, approvals) |
| `worker/` | CLI entry point for running workers (`python -m apps.worker.main`) |

---

## Key Data Flows

### Worker Task Execution
```
WorkerCoordinator.poll_once()
    → claim_next_task() [atomic SELECT FOR UPDATE SKIP LOCKED]
    → create TaskExecution (RUNNING)
    → create TaskLease (TTL + heartbeat)
    → ExecutionService.create_environment() [worktree + sandbox]
    → AgentRuntime.run() [CodingAgent → ToolGateway → Execution]
    → VerificationEngine.verify() [git diff, tests, scope, secrets]
    → SUCCEEDED: TaskExecution SUCCEEDED, Task SUCCEEDED, lease released
    → FAILED: retry (bounded) or FAILED
    → shutdown: drain, release lease
```

### Task Scheduling
```
TaskScheduler.schedule_ready_tasks(mission_id)
    → load tasks + deps
    → for PENDING/BLOCKED tasks:
        → check deps (all SUCCEEDED = ready)
        → atomic try_transition_status: PENDING/BLOCKED → READY → QUEUED
```

### Verification
```
VerificationEngine.verify(context, agent_run_id, worktree_path, execution_id)
    → Git status + diff
    → Tests (explicit test commands only)
    → Scope check (allowed paths)
    → Secret leakage
    → Unexpected changes
    → Acceptance criteria (INCONCLUSIVE = requires explicit eval)
```

---

## Critical Invariants

| Invariant | Enforcement |
|-----------|-------------|
| **No double task ownership** | `SELECT FOR UPDATE SKIP LOCKED` on claim + lease ownership check before every mutation |
| **Stale worker cannot complete** | `_assert_ownership()` re-reads lease before completion |
| **Lease expiry = recovery** | `recover_stale()` finds expired leases, requeues tasks |
| **TaskExecution separate from Task** | `TaskExecutionStatus` enum (CREATED, PENDING, READY, QUEUED, RUNNING, SUCCEEDED, FAILED, RETRYING, BLOCKED, CANCELLED) |
| **No verify-as-test** | Only explicit test commands (`pytest`, `npm test`, etc.) count as tests |
| **Acceptance criteria not auto-pass** | Returns `INCONCLUSIVE` requiring explicit evaluation |
| **Worktree containment** | `resolve_within_directory()` (commonpath + realpath) |
| **PostgreSQL authoritative** | Alembic migrations only; integration tests use `alembic upgrade head` |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Required | PostgreSQL connection string |
| `AURA_ALLOWED_EXECUTABLES` | `git,python,python3,pytest,node,npm,pnpm,uv,ls,echo,cat` | Sandbox allowlist |
| `AURA_MAX_STDOUT_BYTES` | 1MB | Output truncation |
| `AURA_WORKTREE_ROOT` | `~/.aura/worktrees` | Worktree base directory |
| `AURA_WORKER_POLL_INTERVAL` | 5.0s | Worker polling interval |
| `AURA_WORKER_LEASE_TTL` | 90s | Lease time-to-live |
| `AURA_WORKER_HEARTBEAT_INTERVAL` | 30s | Heartbeat interval |
| `AURA_WORKER_SHUTDOWN_TIMEOUT` | 30s | Graceful drain timeout |