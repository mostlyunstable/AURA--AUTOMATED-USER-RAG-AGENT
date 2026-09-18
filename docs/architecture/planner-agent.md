# Planner Agent

## Architecture
The `PlannerAgent` sits between the Mission boundary and the underlying execution systems. It does NOT execute code. It is strictly an intelligence layer that evaluates a Mission, gathers context, and proposes an `EngineeringPlan`.

### Flow
1. **Context Gathering**: Reads `RepositoryContext` and `ForgeContext`.
2. **LLM Generation**: Uses `LLMProvider` to query the LLM via strict JSON schema (`PlannerOutput`).
3. **Validation**:
   - Pydantic Schema Validation (Types, length bounds).
   - DAG Validation (Cycle detection using AURA-002 logic).
4. **Persistence**: Saves the plan to the `plans` table and marks older plans for this mission as `SUPERSEDED`.
5. **Mission Update**: Moves the mission to `PLANNED`.

## Idempotency and Versioning
A mission can only have one active plan. When a new plan is generated, previous plans (even if previously validated) are marked as `SUPERSEDED`. 
