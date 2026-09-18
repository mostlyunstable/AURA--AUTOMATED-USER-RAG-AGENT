# Execution Boundary Security

The AURA Execution Boundary enforces strict security rules to prevent autonomous agents from compromising the host system.

## Git Worktrees
All execution happens inside a generated Git Worktree inside `AURA_WORKTREE_ROOT` (default `~/.aura/worktrees`). The primary repository is untouched.

## Subprocess Execution (Local Sandbox)
*   **No Shell**: `shell=False` is strictly enforced. Execution of `bash -c` is prohibited by the allowlist.
*   **Command Allowlist**: Only explicitly allowed binaries can be executed (e.g., `git`, `pytest`, `python3`).
*   **Path Traversal Prevention**: Working directories and executable arguments are validated against the `AURA_WORKTREE_ROOT`.
*   **Resource Limits**: `AURA_COMMAND_TIMEOUT_SECONDS`, `AURA_MAX_STDOUT_BYTES`, and `AURA_MAX_STDERR_BYTES` prevent infinite loops and memory exhaustion.
*   **Secret Redaction**: Stdout and stderr are scanned for known secrets (API keys) before being returned or persisted.

## Limitations
The current `LocalSandboxManager` relies on OS-level process isolation, not containerization (Docker) or VM-level sandboxing (Firecracker). It provides a strong *application boundary* but a malicious python script could theoretically still access the network or parts of the un-chrooted filesystem. Future phases will introduce stronger containerized backends behind the `SandboxManager` abstraction.
