# AURA — Autonomous Engineering & Agent Runtime

## OpenCode Instructions

AURA is an autonomous engineering platform. Before starting work:

1. **Read AGENTS.md**
2. **Read only the relevant context file(s) under `.opencode/context/`**
3. **Determine the subsystem involved**
4. **Inspect only the relevant source files**
5. **Do NOT scan the entire repository unless the task genuinely requires it**
6. **Use targeted search**
7. **Make minimal changes**
8. **Run targeted tests first**
9. **Run broader tests only when justified**
10. **Update the relevant context file after meaningful architectural changes**

### Workflow

```
CONTEXT
→ TARGETED INSPECTION
→ IMPLEMENT
→ TARGETED TEST
→ DEBUG
→ UPDATE MEMORY
→ CONTINUE
```

### Core Principles

- **The context files are summaries and navigation aids. When they conflict with source code, source code wins.**
- **Do not reread unrelated parts of the repository.**
- **Do not perform broad repository searches unless required by the task.**
- **Do not regenerate or rewrite context files unnecessarily.**

---

### Token-Efficient Search Rules

**RULE 1:** Do not start every task with `find .`, `cat` every file, `grep` the entire repository.

**RULE 2:** Use the context files to identify the subsystem first.

**RULE 3:** Then inspect only:
- relevant interfaces
- relevant implementation
- relevant tests
- immediate dependencies

**RULE 4:** Search exact symbols instead of broad code dumps.
- Instead of reading the entire repository: search `WorkerCoordinator`
- Then inspect: `worker_coordinator.py`, `interfaces.py`, worker entities, repositories, worker tests

**RULE 5:** Do not reread files already understood unless they changed.

**RULE 6:** Prefer targeted commands:
- `git status`
- `git diff -- relevant/path`
- `grep/search specific symbol`
- `pytest specific_test.py`
- `pytest specific_test::test_name`

**RULE 7:** Only escalate to broader inspection when targeted evidence is insufficient.

---

### Navigation Map

| Task Type | Read Context First | Inspect These Areas |
|-----------|-------------------|---------------------|
| **CI / Pipeline** | `current-state.md` + `conventions.md` | `.github/workflows/`, `pyproject.toml`, `tests/`, `alembic.ini`, `alembic/env.py` |
| **Worker / Task Execution** | `architecture.md` + `current-state.md` | `core/application/worker*`, `core/domain/workers/`, `core/infrastructure/database/repositories.py` |
| **Agent / LLM Runtime** | `architecture.md` | `core/application/agent*`, `core/domain/agents/`, `core/infrastructure/llm/` |
| **Database / Migrations** | `architecture.md` + `conventions.md` | `alembic/`, `core/infrastructure/database/`, `tests/integration/` |
| **Verification Engine** | `architecture.md` | `core/application/verification_engine.py`, `core/domain/agents/verification.py`, `tests/unit/test_verification_engine.py` |
| **Tool Gateway / Execution** | `architecture.md` | `core/application/tool_gateway.py`, `core/infrastructure/execution/`, `tests/security/` |
| **Task Scheduling / DAG** | `architecture.md` | `core/application/task_scheduler.py`, `core/domain/tasks/`, `tests/unit/test_task_scheduler.py` |
| **API / HTTP Endpoints** | `architecture.md` | `apps/api/main.py`, `core/application/mission_service.py`, `tests/integration/test_api.py` |

---

### Memory Update Rule

After meaningful work, update **ONLY** the relevant context file:

- Worker architecture changed → `architecture.md`
- New architectural decision → `decisions.md`
- Current phase changed → `current-state.md`
- Roadmap milestone completed → `roadmap.md`

Do NOT rewrite every context file after every task.

---

### Stale Memory Protection

Every context file contains: `LAST VERIFIED: <date/commit>`

When starting a task:
- If context is stale or contradictory → verify only the affected subsystem
- **Do NOT blindly trust memory. Source code always wins.**