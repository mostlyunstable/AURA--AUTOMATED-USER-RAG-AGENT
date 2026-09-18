# Execution Boundary Architecture

AURA-004 introduces the Execution Boundary to establish a secure, deterministic environment where autonomous agents can execute commands and inspect repositories.

## Core Concepts

*   **ExecutionEnvironment**: The domain model representing an isolated environment associated with a TaskExecution. It holds the worktree path, base commit, and lifecycle state.
*   **GitWorktreeManager**: An abstraction for creating isolated git worktrees so that executions do not operate on the primary repository checkout.
*   **SandboxManager**: The executor abstraction. In AURA-004, this is implemented as a local restricted process backend (shell=False, timeouts, path isolation).
*   **ExecutionCommand & CommandResult**: Domain models for representing deterministic commands and capturing their execution (exit code, stdout, stderr, truncation flags).

## Flow
1. A Task is approved for execution.
2. The `ExecutionService` invokes `GitWorktreeManager.create()` to generate a unique worktree inside `AURA_WORKTREE_ROOT`.
3. The `ExecutionService` initializes the `SandboxManager`.
4. Commands are requested via the API, validated by the `SandboxManager`, executed, and the `CommandResult` is persisted.
5. Once the task is completed or failed, `cleanup_environment` removes the worktree.

## Strict Boundaries
*   Domain does not import subprocess, FastAPI, or SQLAlchemy.
*   Execution is completely abstracted.
*   Events are generated for all lifecycle actions.
