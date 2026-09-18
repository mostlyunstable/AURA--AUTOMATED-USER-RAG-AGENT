# Existing System Audit

## 1. Workspace
- **Detected repositories**: `Forge` was found at `/Users/caffinelove/Projects/forge`. No `AEGIS` repository was found locally.
- **Detected technologies**: `Forge` uses Python, FastAPI, SQLAlchemy, Alembic, and a clean architecture structure (`application`, `domain`, `infrastructure`, `presentation`).

## 2. Forge
- **Architecture**: Follows a clean architecture. Uses CQRS/Use Case pattern with repositories. Uses PostgreSQL and Qdrant for vector storage.
- **Reusable APIs**: 
  - `indexing`: API for full/incremental code indexing (`/index/jobs`, `/index/status`).
  - `memory`: API for bugs, decisions, and preferences (`/memory/bugs`, `/memory/decisions`).
  - `analysis`, `code`, `git`, `projects`: Core codebase context and intelligence retrieval.
- **Integration Strategy**: AURA should interact with Forge via its REST API (or an internal HTTP client adapter). AURA will use `ForgeAdapter` in `core/infrastructure/forge/` to communicate with the Forge API to fetch engineering context, project structure, memories, and decisions.

## 3. AEGIS
- **Architecture**: Not present in the local workspace. Based on product vision, it handles durable execution (tasks, checkpoints, recovery, worker leases).
- **Integration Strategy**: Since AEGIS is not available locally, we will define a clean `AgentRuntime` and `AEGISAdapter` abstraction within AURA (`core/infrastructure/aegis/`). For V1, we will use a dummy/local runner or mock adapter until AEGIS is available, ensuring AURA does not reinvent durable execution.

## 4. AURA Proposed Architecture
- **Domain**: Entities for `Mission`, `Task`, `Agent`, `AgentRun`, `ToolCall`, `Event`, `Policy`, `Approval`.
- **Application**: `OrchestratorService`, `MissionService`, `PolicyEngine`.
- **Infrastructure**: Database (PostgreSQL/SQLAlchemy), ForgeAdapter, AegisAdapter, LLMProvider.
- **Presentation**: FastAPI application.

## 5. Risks
- **Durable Execution**: If AEGIS is not available, local execution might lack durability. We must not build a complex durable execution engine in AURA, but rely on an interface.
- **Security**: Autonomous execution carries risks. We need strict policy enforcement in the `ToolGateway`.

## 6. Migration / Adapters
- Implement `ForgeAdapter` mapped to Forge's FastAPI routes.
- Implement `AEGISAdapter` interface, stubbed for now.
