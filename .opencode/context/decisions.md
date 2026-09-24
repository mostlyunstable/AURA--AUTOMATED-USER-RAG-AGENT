# AURA Architecture Decisions

**LAST VERIFIED: 2026-09-21 / d383203**

---

| Date | Decision | Reason | Impact |
|------|----------|--------|--------|
| 2026-09-21 | **PostgreSQL-only integration testing** (no SQLite fallback) | Production schema consistency; SQLite lacks asyncpg, JSONB, proper constraints | Eliminates schema drift; tests run against real production-equivalent schema |
| 2026-09-21 | **Alembic migrations as source of truth** (no `create_all()` in integration tests) | ORM metadata can hide migration errors; migrations must work on fresh DB | Guarantees migration correctness; catches schema mismatches early |
| 2026-09-21 | **TaskExecutionStatus separate from TaskStatus** | Task execution has different lifecycle (CREATED→PENDING→RUNNING→SUCCEEDED/FAILED) vs task planning (PENDING→READY→QUEUED) | Clearer semantics; prevents state conflation; enables retry semantics |
| 2026-09-21 | **Atomic task claiming with `SELECT FOR UPDATE SKIP LOCKED`** | Prevents double ownership under concurrent workers | Guarantees single ownership; eliminates race conditions |
| 2026-09-21 | **Lease ownership validation before every mutation** (`_assert_ownership()`) | Stale workers must not complete tasks after lease expiry/recovery | Eliminates stale-worker corruption; critical for correctness |
| 2026-09-21 | **ToolGateway as mandatory policy boundary** | Centralizes capability checks, worktree containment, audit logging | Prevents bypasses; single point of security enforcement |
| 2026-09-21 | **Worktree path containment via `commonpath` + `realpath`** | `startswith()` allows prefix collisions (`/worktree-other`); symlinks can escape | Prevents directory traversal; defense-in-depth |
| 2026-09-21 | **Verification test detection = explicit test commands only** | `exit_code == 0` incorrectly treated `echo`, `ls`, `python script.py` as passing tests | Eliminates false verification passes |
| 2026-09-21 | **Acceptance criteria returns `INCONCLUSIVE` (not `PASSED`)** | Auto-passing hides missing evaluation logic | Forces explicit criteria evaluation; prevents silent success |
| 2026-09-21 | **PR validation requires execution SUCCEEDED + verification PASSED** | Previously only checked mission status = VERIFIED | Prevents PR creation for incomplete/unverified work |
| 2026-09-21 | **Integration tests use Alembic migrations** (`upgrade head` / `downgrade base`) | `Base.metadata.create_all()` bypasses migration logic | Catches migration errors; ensures ORM/migration parity |
| 2026-09-20 | **TaskScheduler uses atomic `try_transition_status`** | Previous read-check-write had race condition | Prevents duplicate scheduling; ensures idempotency |
| 2026-09-20 | **Alembic `env.py` uses ThreadPoolExecutor for asyncio.run in running loop** | `asyncio.run()` fails when pytest event loop already running | Allows Alembic to work in both CLI and pytest contexts |
| 2026-09-20 | **Worker CLI uses asyncio.run in ThreadPoolExecutor for Alembic** | Same event loop conflict when running migrations from worker | Allows worker to run migrations at startup |
| 2026-09-20 | **Metadata column naming: `metadata_` in ORM → `metadata` in DB** | SQLAlchemy `metadata` is reserved; migration renamed `metadata_` → `metadata` | ORM/Db parity; consistent with historical migrations |
| 2026-09-19 | **Clean Architecture: Domain → Application → Infrastructure** | Prevents framework leakage into domain; testability | Domain stays pure; infrastructure swappable |
| 2026-09-19 | **UnitOfWork pattern for transaction management** | Explicit transaction boundaries; rollback on failure | Consistent DB semantics; testable with mocks |
| 2026-09-18 | **Prometheus metrics for all critical paths** | Observability from day one | Debugging, alerting, capacity planning |
| 2026-09-18 | **Structured logging with structlog** | Consistent log format; correlation IDs ready | Debugging, audit trails |
| 2026-09-18 | **No shell=True in subprocess execution** | Command injection prevention | Security baseline |
| 2026-09-18 | **Process group kill on timeout (SIGKILL)** | Child processes can survive `process.kill()` | Prevents zombie processes; resource cleanup |