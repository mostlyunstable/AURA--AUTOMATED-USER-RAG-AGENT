# AURA Engineering Conventions

**LAST VERIFIED: 2026-09-21 / d383203**

## Architecture

- **Clean Architecture**: Domain → Application → Infrastructure
- **Domain layer**: Pure Python, zero external dependencies
- **Application layer**: Orchestration only, no framework code
- **Infrastructure layer**: Implements application interfaces (SQLAlchemy, FastAPI, LLM SDKs, etc.)

---

## Database

- **PostgreSQL is authoritative** — schema defined by Alembic migrations only
- **Integration tests MUST use `alembic upgrade head`** — never `Base.metadata.create_all()`
- **Alembic migrations are the source of truth** for production schema
- **UnitOfWork pattern** for transaction management (`core/application/interfaces.py`)
- **Repository interfaces** in application layer; implementations in infrastructure

---

## Worker / Task Execution

- **Atomic task claiming**: `SELECT FOR UPDATE SKIP LOCKED` via `try_transition_status`
- **Lease ownership validated** before every state mutation (`_assert_ownership()`)
- **Lease expiry = recovery**: `recover_stale()` requeues tasks, blocks stale completion
- **TaskExecution ≠ Task**: `TaskExecutionStatus` enum (CREATED, PENDING, READY, QUEUED, RUNNING, SUCCEEDED, FAILED, RETRYING, BLOCKED, CANCELLED)
- **Stale worker cannot complete**: `_assert_ownership()` re-reads lease before completion
- **Graceful shutdown**: Drain in-flight work, release leases, mark STOPPED

---

## Verification

- **Independent**: Agent cannot declare itself successful
- **Test detection**: Only explicit test commands (`pytest`, `npm test`, `go test`, `cargo test`) count
- **No auto-pass**: Acceptance criteria returns `INCONCLUSIVE` (requires explicit evaluation)
- **Checks**: Git status, git diff, tests, scope, secrets, unexpected changes, policy violations, execution failures

---

## Security / Execution

- **ToolGateway mandatory**: All tool calls route through `ToolGateway` (policy + worktree containment)
- **Workers never bypass ExecutionService**: `WorkerCoordinator → AgentRuntime → ToolGateway → ExecutionService`
- **Worktree containment**: `resolve_within_directory()` (commonpath + realpath) — prevents `/worktree-other` and symlink escapes
- **Sandbox allowlist**: `AURA_ALLOWED_EXECUTABLES` (default: `git,python,python3,pytest,node,npm,pnpm,uv,ls,echo,cat`)
- **Argument validation**: Rejects `git -C`, `--git-dir`, `--work-tree`, and path-like args for code executables
- **Process tree kill**: `start_new_session=True` + `os.killpg(SIGKILL)` on timeout
- **No shell=True**: Commands executed via `asyncio.create_subprocess_exec` with explicit args
- **Secrets redacted**: API keys, tokens, DB URLs stripped from output

---

## PR / GitHub

- **PR validation**: Execution must be SUCCEEDED + verification PASSED
- **Mission ownership**: Cross-mission PR requests return 403/404
- **No unverified merges**: Merge requires human approval gate

---

## Testing

- **Architecture tests**: Enforce layer boundaries (domain no infra/framework imports)
- **Security tests**: Path traversal, symlink escape, git -C, prefix collision, command injection
- **Integration tests**: Use `alembic upgrade head` / `downgrade base` via `tests/integration/conftest.py`
- **No test weakening**: Do not use `xfail`, `skip`, or weakened assertions to make CI pass
- **PostgreSQL required**: `TEST_DATABASE_URL` must point to PostgreSQL; SQLite fallback disabled

---

## Code Quality

- **Black** (line length 79, py312 target)
- **isort** (black profile)
- **mypy** (strict, but `repositories.py` and `alembic/` excluded)
- **Run before commit**: `mypy core/ && black --check . && isort --check-only .`

---

## Git / Commits

- **Focused commits**: One logical change per commit
- **No secrets**: Never commit `.env`, keys, tokens, databases
- **Conventional messages**: `AURA-XXX: Description`
- **CI must pass locally first**: Never push broken code

---

## Dependency Management

- **uv for package management**: `uv sync --all-extras`
- **Lockfile committed**: `uv.lock` in repository
- **Python ≥ 3.12** required