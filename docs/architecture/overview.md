# Architecture Overview

AURA uses a Hexagonal/Clean Architecture:
- `core/domain`: Framework-independent entities, enums, state machine.
- `core/application`: MissionService orchestrates logic, validates state transitions, defines Repository interfaces.
- `core/infrastructure`: DB Repositories, Alembic migrations, Logging configuration.
- `apps/api`: FastAPI entry points relying on MissionService via DI.

Dependency flow is inward: API -> Application -> Domain.
