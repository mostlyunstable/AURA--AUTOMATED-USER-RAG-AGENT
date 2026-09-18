# AURA-004: Sandbox + Git Worktree Runtime Boundary Implementation Plan

## Goal Description
Implement the Execution Boundary (Sandbox + Git Worktree) for AURA. This includes creating `ExecutionEnvironment`, `GitWorktreeManager`, `SandboxManager`, and `ExecutionCommand` abstractions. It ensures future coding agents execute commands inside an isolated environment (Git worktree) without having arbitrary shell access.

## User Review Required
> [!IMPORTANT]
> The sandbox will use local restricted processes with timeouts, environment filtering, and strict argument validation. It is explicitly NOT a full container/VM runtime yet, but serves as the interface boundary.
> AURA_WORKTREE_ROOT will default to `~/.aura/worktrees/` but can be overridden.

## Open Questions
- Is `~/.aura/worktrees/` acceptable as the default workspace root for this phase?

## Proposed Changes

### Domain Layer (`core/domain/execution/`)
- **`enums.py`**: `EnvironmentStatus` (CREATING, READY, RUNNING, FAILED, CLEANING_UP, DESTROYED), `CommandStatus` (SUCCEEDED, FAILED, TIMED_OUT, REJECTED), `ArtifactType`.
- **`entities.py`**: `ExecutionEnvironment`, `ExecutionCommand`, `CommandResult`, `Artifact`.
- **`interfaces.py`**: `GitWorktreeManager`, `SandboxManager`, `ExecutionEnvironmentManager`.

### Application Layer (`core/application/`)
- **`execution_service.py`**: Handles business logic for creating/destroying execution environments, requesting commands via Sandbox, logging events, and collecting artifacts.
- **`interfaces.py`**: Update `UnitOfWork` to include `execution_environments`, `command_executions`, and `artifacts` repositories.

### Infrastructure Layer (`core/infrastructure/`)
- **`execution/git_worktree.py`**: Implements `GitWorktreeManager`. Uses strict `subprocess.run(["git", ...], shell=False)`. Validates paths.
- **`execution/local_sandbox.py`**: Implements `SandboxManager`. Runs commands (`subprocess.run(shell=False)`), enforces allowlist (`AURA_ALLOWED_EXECUTABLES`), redacts secrets, sets timeouts, restricts environment variables.
- **`database/models.py`**: Add `ExecutionEnvironmentModel`, `CommandExecutionModel`, `ArtifactModel`.
- **`database/repositories.py`**: Implement repositories for the new models.

### API Layer
- **`apps/api/main.py`**: Add structured endpoints for execution (e.g. `POST /tasks/{id}/environment`, `POST /environments/{id}/execute`, `DELETE /environments/{id}`) protected by logic to ensure the task/mission is `APPROVED_FOR_EXECUTION`.

## Verification Plan
### Automated Tests
- **Security Tests**: Test path traversal, shell injection, protected paths, command allowlist evasion.
- **Git Tests**: Create a temp git repo and test worktree creation/deletion/dirty checking.
- **Application & API Tests**: Ensure the `ExecutionService` transitions properly and rejects unauthorized commands.

### Manual Verification
- Will verify end-to-end environment creation and cleanup.
