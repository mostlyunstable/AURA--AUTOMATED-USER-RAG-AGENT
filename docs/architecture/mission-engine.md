# Mission Engine

## Overview
AURA-002 upgrades the Mission CRUD system into a DAG-based Task execution orchestrator. 

## Key Entities
- **Mission**: The top-level objective.
- **Task**: An actionable sub-goal (e.g. ANALYSIS, PLANNING, CODE_REVIEW).
- **TaskDependency**: Tracks execution order (Task B depends on Task A).
- **TaskExecution**: An attempt to complete a task. Maintains history (retries).
- **Approval**: Represents a security or human boundary (e.g., transition into EXECUTING).

## Orchestration
- **TaskScheduler**: Calculates `READY` states based on successful dependencies.
- **MissionOrchestrator**: Manages Task additions and ensures the DAG remains cycle-free.
- **AgentRuntime**: An interface where actual AI execution will occur (plugged in during AURA-003).

## Validation & Cycle Detection
Task dependencies are explicitly validated via `DAGValidator` during insertion to prevent cycles (e.g., A -> B -> A). Self-dependencies are rejected.
