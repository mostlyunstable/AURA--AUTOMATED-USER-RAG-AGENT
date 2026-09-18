# ADR 001: Separate Orchestration from MissionService

## Context
As AURA grows from a state-machine wrapper into a full-fledged Mission Engine, the number of concerns around Tasks, Dependencies, and Agent Assignment increases significantly.

## Decision
We separated orchestration concerns into a `MissionOrchestrator` and `TaskScheduler`, explicitly avoiding bloating the `MissionService`.

## Consequences
- Better Single Responsibility Principle compliance.
- `MissionService` only handles Mission-level lifecycle and top-level approvals.
- DAG validation and scheduling logic live in their respective sub-components.
