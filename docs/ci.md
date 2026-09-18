# AURA CI/CD Documentation

## Triggers
- **Push**: Runs on all branch pushes (`**`).
- **Pull Request**: Runs on PRs targeting `main`.
- **Workflow Dispatch**: Allows manual execution.

## Test Environment
- **OS**: Ubuntu Latest
- **Python**: 3.12 (matches `pyproject.toml`)
- **Package Manager**: `uv` with cache enabled for rapid dependency installation (`uv pip install --system -e ".[dev]"`).

## PostgreSQL Database
- **Service Container**: `postgres:15`
- **Credentials**: Ephemeral CI credentials (`aura:aura@localhost:5432/aura`).
- **Health Check**: Uses `pg_isready` to ensure the database is fully initialized before migrations and tests begin.
- **Strictness**: SQLite is explicitly prohibited; all integration tests rely on this PostgreSQL container to match production behavior.

## Migrations
- Runs `alembic upgrade head` on the clean CI database. If migrations fail, the workflow fails immediately.

## Quality Checks
- **Formatting**: `black --check .`
- **Import Sorting**: `isort --check-only .`
- **Type Checking**: `mypy .`
- **Note**: These checks are non-destructive in CI. They will fail the pipeline if the repository is out of compliance, prompting the developer/agent to fix them locally.

## Tests
Executes the following test categories specifically to preserve targeted boundaries:
- `pytest tests/architecture`: Validates domain/infrastructure strict boundaries.
- `pytest tests/security`: Tests path traversals, shell injections, bounds, and permissions.
- `pytest tests/unit`: Tests state machines and localized logic.
- `pytest tests/integration`: Tests workflows spanning API, DB, and Sandbox.

## LLM Token Efficiency
The authoritative test suite is moved to GitHub Actions to prevent AURA agents from running extensive and expensive test matrices locally. 
**Local Testing Policy**: Agents should run targeted checks (e.g. `pytest tests/unit/test_specific.py`) when developing. 
**CI Failure Workflow**: If GitHub Actions fails, inspect the specific failed job, reproduce locally ONLY if necessary, and push the targeted fix.

## Security 
- **Secrets**: No production secrets (like `NVIDIA_API_KEY`) are exposed to standard CI operations. The `FakeLLMProvider` ensures deterministic, fast, and cheap testing.
- **Permissions**: The workflow uses default least-privilege token access.

