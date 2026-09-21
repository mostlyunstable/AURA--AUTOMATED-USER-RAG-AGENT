# AURA Current State

**LAST VERIFIED: 2026-09-21 / d383203 (AURA-008)**

## Repository State

| Property | Value |
|----------|-------|
| Branch | `main` |
| Commit | `d38320364c56039756abcb1665d476ccd1eefcc7` |
| Upstream | `origin/main` (up to date) |

---

## Completed Phases

| Phase | Status | Commit |
|-------|--------|--------|
| AURA-004: Execution Boundary | ✅ | a0acbf5 |
| AURA-005: Coding Agent Runtime | ✅ | 0f9c088 |
| AURA-006: Duplicate Repo Classes + Integration Tests | ✅ | 112a76c |
| AURA-007: PR Creation + Human Approval + Merge | ✅ | 69bb449 / a6f4eeb |
| AURA-008: Durable Worker Pool + Task Claiming | ✅ | d383203 |
| AURA-009: Worker Orchestration + Real Execution | ✅ | *uncommitted* |

---

## Current Working Subsystem

**Worker Orchestration (AURA-009)** - Complete and locally verified.

### Implemented
- `WorkerCoordinator`: full worker lifecycle (register → poll → claim → lease → heartbeat → execute → verify → complete/retry/fail → release)
- Atomic task claiming via `SELECT FOR UPDATE SKIP LOCKED`
- Lease management (TTL, heartbeat, renewal, expiry detection)
- Stale lease recovery (requeues tasks, blocks stale worker completion)
- Graceful shutdown with drain
- `TaskExecutionStatus` enum (separate from `TaskStatus`)
- Verification test detection fixed (only explicit test commands)
- Acceptance criteria returns `INCONCLUSIVE`
- PR validation: requires execution SUCCEEDED + verification passed
- Worktree cleanup errors propagated
- Integration tests use Alembic migrations (`alembic upgrade head` / `downgrade base`)

### New Files
- `core/application/worker_coordinator.py`
- `apps/worker/main.py` (CLI entry point)
- `core/infrastructure/execution/paths.py` (shared path containment)
- `tests/unit/test_worker_coordinator.py`
- `tests/unit/test_task_scheduler.py` (atomic transitions)
- `tests/unit/test_execution_idempotency.py`
- `tests/integration/conftest.py` (Alembic-based fixtures)

---

## Test Baseline (Local)

| Suite | Tests | Status |
|-------|-------|--------|
| Architecture | 2 | ✅ |
| Security | 23 | ✅ |
| Unit | 53 | ✅ |
| Integration | 17 | ✅ |
| **Total** | **95** | **✅** |

### Quality Gates
| Check | Status |
|-------|--------|
| mypy (core/) | ✅ 0 errors (57 files) |
| black | ✅ clean |
| isort | ✅ clean |
| uv lock | ✅ 48 packages |
| **CI Pipeline** | ✅ **Fixed** (mypy now runs on `core/` only) |

---

## Known Incomplete Areas

| Area | Status | Notes |
|------|--------|-------|
| **GitHub Provider** | Not started | AURA-010 scope |
| **GitHub Webhooks** | Not started | AURA-010 scope |
| **Multi-Agent Orchestration** | Not started | Post-AURA-010 |
| **Authentication/Authorization** | Not implemented | API has no auth |
| **Production Deployment** | Not prepared | No Dockerfile, no K8s |
| **Observability** | Partial | Prometheus metrics exist, no distributed tracing |

---

## Known Technical Debt

| Item | Impact | Priority |
|------|--------|----------|
| `core/infrastructure/database/repositories.py` excluded from mypy | Type safety gaps | Medium |
| `mypy.ini` excludes `repositories.py` and `alembic/` | Reduced type coverage | Low |
| Fake LLM provider in tests | Not production-realistic | Low (by design) |
| No structured logging correlation IDs | Debugging harder | Low |
| Worker CLI uses synchronous `asyncio.run` in thread pool for Alembic | Event loop workaround | Low |

---

## Immediate Objective

**AURA-009 complete. Ready for AURA-010 (GitHub Provider Integration).**

Next steps when starting AURA-010:
1. Implement `GitHubProvider` interface in `core/infrastructure/github/`
2. Add webhook endpoint in `apps/api/main.py`
3. Implement PR creation/update via GitHub API
4. Add webhook signature verification
5. Add integration tests against real GitHub (or mock)