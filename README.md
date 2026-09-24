# AURA — Autonomous Engineering & Agent Runtime

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Build Status](https://github.com/mostlyunstable/AURA--AUTOMATED-USER-RAG-AGENT/actions/workflows/ci.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)

A production-grade **autonomous software-engineering orchestration platform** that transforms engineering intent into verified, reviewed, and merged code through coordinated multi-agent workflows.

---

## 🎯 What is AURA?

AURA (Autonomous Engineering & Agent Runtime) is a platform that takes high-level engineering intent and autonomously executes the complete software development lifecycle:

```
MISSION → PLANNER → TASK GRAPH → MULTI-AGENT ORCHESTRATION
    ↓
CODER → DEBUGGER → TESTER → VERIFIER → SECURITY REVIEWER → CODE REVIEWER
    ↓
PR CREATION → HUMAN APPROVAL → MERGE → POST-MERGE VERIFICATION
```

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **Multi-Agent Orchestration** | Coordinated specialized agents (Planner, Coder, Debugger, Tester, Security Reviewer, Code Reviewer) executing as a DAG |
| **Durable Worker Pool** | Lease-based task claiming with heartbeats, stale detection, and automatic recovery |
| **RAG/Context Engine** | Forge-integrated retrieval for semantic, lexical, symbol, and dependency-aware context |
| **Isolated Execution** | Git worktrees, sandboxed subprocess execution, capability-gated tool gateway |
| **Independent Verification** | Git diff, test execution, scope checking, secret scanning, secret leakage detection |
| **GitHub Integration** | PR creation, webhook processing, check runs, review synchronization |
| **Human-in-the-Loop** | Approval gates for plan, execution, merge, and security overrides |
| **Observability** | Prometheus metrics, structured logging, distributed tracing ready |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AURA Platform                            │
├─────────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                            │
│  ├─ /missions         Mission CRUD, state transitions           │
│  ├─ /tasks            Task CRUD, dependencies, scheduling       │
│  ├─ /executions       Worktree, sandbox, command execution      │
│  ├─ /agents           Multi-agent workflow orchestration        │
│  ├─ /webhooks/github  GitHub webhook ingestion                  │
│  └─ /health, /metrics Prometheus metrics, health checks         │
├─────────────────────────────────────────────────────────────────┤
│  Application Layer (Clean Architecture)                         │
│  ├─ MissionService         Mission lifecycle, approvals         │
│  ├─ TaskScheduler          DAG scheduling, atomic transitions   │
│  ├─ WorkerCoordinator      Worker lifecycle, leases, recovery   │
│  ├─ AgentCoordinator       Multi-agent DAG orchestration        │
│  ├─ PlannerAgent           Engineering plan generation          │
│  ├─ CodingAgent            Code implementation, tool use        │
│  ├─ VerificationEngine     Independent verification (tests, diff, secrets) │
│  ├─ ContextRetrievalService  RAG/Forge integration              │
│  └─ RecoveryEngine         Stale lease detection, requeue       │
├─────────────────────────────────────────────────────────────────┤
│  Domain Layer (Pure Python)                                     │
│  ├─ Missions, Tasks, Agents, Workers, PRs, Approvals           │
│  ├─ State Machines (Mission, Task, AgentRun, AgentTask)         │
│  └─ Events, Metrics, Policies                                   │
├─────────────────────────────────────────────────────────────────┤
│  Infrastructure Layer                                           │
│  ├─ PostgreSQL + SQLAlchemy (async) + Alembic migrations        │
│  ├─ GitHub Provider (REST API, webhooks, check runs)            │
│  ├─ Local Execution (Git worktrees, sandbox, artifact collector)│
│  ├─ Forge Adapter (semantic/lexical/symbol search, RAG)         │
│  └─ LLM Providers (NVIDIA, Fake for testing)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- PostgreSQL 15+ (via Docker)
- uv (recommended) or pip

### Installation

```bash
# 1. Clone repository
git clone https://github.com/mostlyunstable/AURA--AUTOMATED-USER-RAG-AGENT.git
cd AURA--AUTOMATED-USER-RAG-AGENT

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies (using uv for speed)
uv sync --all-extras
# OR: pip install -e ".[dev]"

# 4. Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL, NVIDIA_API_KEY, etc.

# 5. Start PostgreSQL
docker compose up -d db

# 6. Run database migrations
alembic upgrade head

# 7. Start API server
uvicorn apps.api.main:app --reload

# 8. (Optional) Start a worker
python -m apps.worker.main --mission-id <MISSION_ID> --count 2
```

### Run Tests
```bash
# All tests (requires PostgreSQL)
pytest tests/ tests/integration/

# Unit tests only
pytest tests/unit/

# Security tests
pytest tests/security/

# Architecture tests
pytest tests/architecture/
```

---

## 🔧 Configuration

Key environment variables (see `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL async connection string |
| `NVIDIA_API_KEY` | No | - | NVIDIA LLM API key (uses FakeLLM if absent) |
| `GITHUB_TOKEN` | No | - | GitHub PAT for PR operations |
| `GITHUB_WEBHOOK_SECRET` | No | - | HMAC secret for webhook verification |
| `AURA_WORKTREE_ROOT` | No | `~/.aura/worktrees` | Base directory for git worktrees |
| `AURA_WORKER_LEASE_TTL` | No | `90` | Worker lease TTL in seconds |
| `AURA_WORKER_HEARTBEAT_INTERVAL` | No | `30` | Worker heartbeat interval (seconds) |
| `AURA_MAX_STDOUT_BYTES` | No | `1048576` | Max stdout capture (1MB) |

---

## 🧪 Usage Examples

### Create a Mission
```bash
curl -X POST http://localhost:8000/missions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add user authentication",
    "description": "Implement JWT-based auth with refresh tokens",
    "repository_id": "myorg/myapp",
    "source": "github"
  }'
```

### Generate a Plan
```bash
curl -X POST http://localhost:8000/missions/{mission_id}/plan
```

### Approve Execution
```bash
curl -X POST http://localhost:8000/missions/{mission_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approval_type": "EXECUTION"}'
```

### Create Environment & Execute
```bash
# Create execution environment
curl -X POST http://localhost:8000/tasks/{task_id}/executions/{execution_id}/environment \
  -H "Content-Type: application/json" \
  -d '{"mission_id": "...", "repository_id": "myorg/myapp"}'

# Execute commands in the worktree
curl -X POST http://localhost:8000/environments/{env_id}/execute \
  -H "Content-Type: application/json" \
  -d '{
    "executable": "pytest",
    "arguments": ["tests/", "-v"],
    "working_directory": "/worktree",
    "timeout_seconds": 120
  }'
```

### Create PR via GitHub
```bash
curl -X POST http://localhost:8000/missions/{mission_id}/pr \
  -H "Content-Type: application/json" \
  -d '{
    "task_execution_id": "...",
    "source_branch": "feature/auth",
    "title": "Add JWT authentication",
    "description": "Implements JWT auth with refresh tokens"
  }'
```

### GitHub Webhook
Configure GitHub webhook to `POST /webhooks/github` with events:
- `pull_request` (opened, closed, reopened, synchronize)
- `pull_request_review` (submitted, dismissed)
- `check_run` (completed, rerequested)
- `push`

---

## 🧪 Testing

```bash
# All tests (requires PostgreSQL)
TEST_DATABASE_URL=postgresql+asyncpg://aura:aura@localhost:5432/aura pytest tests/ tests/integration/

# Unit tests only
pytest tests/unit/

# Security-focused tests
pytest tests/security/

# Architecture compliance
pytest tests/architecture/

# With coverage
pytest --cov=core --cov-report=html
```

---

## 🔒 Security

- **No shell=True** - All commands via `asyncio.create_subprocess_exec`
- **Path containment** - `resolve_within_directory()` (commonpath + realpath)
- **Executable allowlist** - `AURA_ALLOWED_EXECUTABLES`
- **Argument validation** - Rejects `git -C`, `--git-dir`, path traversal
- **Process tree kill** - `SIGKILL` on timeout via process groups
- **Secret redaction** - API keys, tokens, DB URLs stripped from logs
- **Webhook verification** - HMAC-SHA256 signature validation
- **Path containment** - Worktree isolation via git worktrees

---

## 📊 Observability

- **Prometheus metrics** at `/metrics`
- **Structured logging** via structlog (JSON, correlation IDs)
- **Key metrics**: mission duration, task queue depth, worker utilization, agent runs, tool calls, verification latency, LLM token usage

---

## 🛣 Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| AURA-001 to 009 | ✅ Complete | Foundation (Mission, Task, Worker, Agent, Execution, Verification) |
| **AURA-010** | ✅ Complete | **GitHub Provider** (PR, webhooks, check runs) |
| **AURA-011** | 🚧 In Progress | **Multi-Agent Orchestration** (Debugger, Tester, Security Reviewer) |
| AURA-012 | 📋 Planned | Agent Recovery (bounded retries, failure classification) |
| AURA-013 | 📋 Planned | Code Review Agent |
| AURA-014 | 📋 Planned | Security Review Agent |
| AURA-015 | 📋 Planned | Authentication/Authorization |
| AURA-016 | 📋 Planned | Production Deployment (Docker, K8s) |
| AURA-017 | 📋 Planned | Observability (tracing, correlation IDs) |

---

## 📁 Project Structure

```
AURA/
├── AGENTS.md                    # OpenCode agent instructions
├── .opencode/context/           # Persistent project memory
│   ├── architecture.md          # System architecture
│   ├── current-state.md         # Current implementation status
│   ├── conventions.md           # Engineering conventions
│   ├── roadmap.md               # Phase roadmap
│   └── decisions.md             # Architecture decision records
├── apps/
│   ├── api/                     # FastAPI application
│   └── worker/                  # Worker CLI entry point
├── core/
│   ├── application/             # Orchestration services
│   │   ├── agent_coordinator.py   (planned)
│   │   ├── agent_runtime.py
│   │   ├── coding_agent.py
│   │   ├── planner_agent.py
│   │   ├── task_scheduler.py
│   │   ├── worker_coordinator.py
│   │   ├── verification_engine.py
│   │   └── rag/                     # RAG engine
│   ├── domain/                  # Pure domain models
│   │   ├── agents/              # Agent, AgentRun, AgentTask, AgentWorkflow
│   │   ├── missions/            # Mission, Plan, Approval
│   │   ├── tasks/               # Task, TaskExecution, TaskDependency
│   │   ├── workers/             # Worker, TaskLease, WorkerHeartbeat
│   │   ├── execution/           # ExecutionEnvironment, Command, Artifact
│   │   ├── pull_requests/       # PR entities
│   │   └── agents/orchestration/  # AgentTask, AgentWorkflow, AgentMessage
│   └── infrastructure/          # Adapters
│       ├── database/            # SQLAlchemy, Alembic, UnitOfWork
│       ├── execution/           # Sandbox, Git worktree, Artifacts
│       ├── github/              # GitHub REST API, webhooks
│       ├── forge/               # RAG/Context retrieval
│       ├── llm/                 # NVIDIA, Fake LLM providers
│       └── logging/             # Structured logging
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests (Alembic + Postgres)
│   ├── security/                # Security boundary tests
│   └── architecture/            # Architecture compliance tests
├── alembic/                     # Database migrations
├── .github/workflows/           # CI/CD pipelines
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes with tests
4. Run quality checks: `black --check . && isort --check-only . && mypy core/`
5. Run tests: `pytest tests/ tests/integration/`
6. Submit a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Async ORM
- [Alembic](https://alembic.sqlalchemy.org/) - Database migrations
- [Prometheus Client](https://github.com/prometheus/client_python) - Metrics
- [structlog](https://www.structlog.org/) - Structured logging
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer

---

**AURA** — Turning engineering intent into verified, production-ready code. 🚀