# AURA — Project Context (paste into any open-source agent)

## 1. What this is
AURA = Autonomous Engineering & Agent Runtime. A FastAPI + Postgres orchestration
platform for autonomous software-engineering missions. NOT a RAG agent.
Repo: mostlyunstable/AURA--AUTOMATED-USER-RAG-AGENT. Branch for anku: `aura/anku-dev`.
`main` is stable (mostlyunstable). Never commit directly to `main` from anku work.

## 2. Stack
Python 3.12+, FastAPI >=0.110, uvicorn[standard], SQLAlchemy[asyncio] 2.0 + asyncpg,
Alembic, Pydantic v2 + pydantic-settings, structlog, prometheus-client.
Dev: pytest + pytest-asyncio + httpx, black, isort (profile=black), mypy.
Infra: Postgres 15 (docker compose `db`), Alembic migrations in `alembic/versions/`
(AURA-002..008). No Dockerfile yet (TODO Phase 1). `uv sync --all-extras`, `uv run`.

## 3. Architecture (mandatory)
Hexagonal / Clean. Dependency flow inward: `apps/api -> core/application -> core/domain`.
- `core/domain/`: pure entities/enums/state_machines/protocols. FORBIDDEN imports:
  fastapi, sqlalchemy, core.infrastructure, apps, subprocess. Enforced by
  `tests/architecture/test_architecture.py`.
- `core/application/`: services (MissionService, ExecutionService, PlannerAgent,
  CodingAgent, AgentRuntime, ToolGatewayImpl, VerificationEngine, TaskScheduler,
  MissionOrchestrator). FORBIDDEN: fastapi, sqlalchemy.
- `core/infrastructure/`: sqlalchemy models/repos, local_sandbox, git_worktree,
  llm providers, context adapters, logging, metrics.
- `apps/api/main.py`: FastAPI routes only, thin, DI via UnitOfWork.
- `agents/`, `policies/` empty (.gitkeep). `integrations/aegis/` placeholder.

## 4. Key files
- API: `apps/api/main.py` (598 lines, needs router split)
- DB: `core/infrastructure/database/models.py`, `repositories.py` (2146 lines GOD FILE,
  has `# mypy: ignore-errors`, excluded in mypy.ini — needs per-aggregate split)
- Domain index: `core/domain/__init__.py`
- Execution: `core/infrastructure/execution/local_sandbox.py` (allowlist via
  AURA_ALLOWED_EXECUTABLES, shell=False, timeout, env denylist, naive redact),
  `git_worktree.py`, `artifact_collector.py`
- Gateway: `core/application/tool_gateway.py` (policy + realpath containment;
  fix `startswith(worktree_abs)` to use `os.sep` suffix)
- Verify: `core/application/verification_engine.py` (733 lines)
- LLM: `core/domain/llm/interfaces.py`, `core/infrastructure/llm/fake_provider.py`,
  `nvidia_provider.py` (only real one; OPENAI/ANTHROPIC/GEMINI keys in .env but unimplemented)
- Context stubs: `core/infrastructure/context/forge_adapter.py`,
  `repository_adapter.py` (both Stub, return hardcoded memories)
- Config: `pyproject.toml`, `mypy.ini`, `pytest.ini` (asyncio_mode=strict),
  `alembic.ini`, `docker-compose.yml` (build:. broken — no Dockerfile),
  `.env.example` (DATABASE_URL, REDIS_URL unused, FORGE_URL/AEGIS_URL unused)
- Tests: `tests/architecture|security|unit|integration` (need Postgres).
  CI `.github/workflows/ci.yml`: black --check, isort --check, mypy, alembic upgrade head,
  then 4 pytest suites.

## 5. Conventions for any agent
- Python 3.12, type hints required, black + isort, `shell=False` only, no secrets in logs.
- Never add `*.bak`, never commit `__pycache__/.env/*.db`. Work on branch
  `aura/anku-dev`, rebase on `origin/main` before PR: `git fetch; git rebase origin/main`.
- Small PRs <200 lines. Update Alembic migration for model changes.
- Mission lifecycle (strict state machine): CREATED->PLANNING->PLANNED->
  APPROVED_FOR_EXECUTION->EXECUTING->VERIFYING->VERIFIED->PR_READY->
  AWAITING_HUMAN_APPROVAL->MERGED. Use append-only Events for transitions.

## 6. Leftover work (in order)
P1 Dockerfile + compose: add Dockerfile (3.12-slim, uv sync, uvicorn apps.api.main:app),
  fix compose, wire DATABASE_URL/REDIS/FORGE/AEGIS via env.
P2 Debt split: repositories.py -> per-aggregate files (mission/task/plan/agent/execution/
  worker/approval/pr), remove mypy ignore; main.py -> routers/ (missions/tasks/plans/
  approvals/environments/system).
P3 Real adapters: ForgeAdapter HTTP client to FORGE_URL (/index,/memory,/code),
  RepositoryContext via git; OpenAIProvider (+Anthropic) mirroring NvidiaLLMProvider.
P4 AEGIS + agents/policies: implement `integrations/aegis/` adapter to AEGIS_URL,
  fill `agents/` (registry) and `policies/` (OPA-style allow/deny) + ToolGateway wiring.
P5 Hardening: path `startswith(x + os.sep)`, regex secret redact, container sandbox
  option, expand README + implementation_plan beyond AURA-004.

## 7. Copy-paste prompt starter for any agent
"Read PROJECT_CONTEXT.md. You are working in C:\aether\AURA on branch aura/anku-dev
(Python 3.12, FastAPI, SQLAlchemy async, Postgres). Respect Clean Architecture:
domain pure, no fastapi/sqlalchemy/subprocess in core/domain. Task: <P1|P2|...>.
Run `uv run black --check .`, `uv run isort --check-only .`, `uv run mypy .`,
`uv run pytest tests/architecture tests/security tests/unit`. Keep diff <200 lines,
no *.bak, update Alembic if models change. Output files changed + tests run."

## 8. Branch map (no-conflict rule)
- `main`: mostlyunstable, stable, PR squash merges only.
- `aura/anku-dev`: anku (you are here). All anku work here.
- Future: `aura/mostlyunstable-dev` if needed. Integrate via fetch + rebase + squash PR,
  one at a time. `git fetch --all` to see both without merging.
