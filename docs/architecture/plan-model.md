# Plan Domain Model

Plans are strongly typed, validated objects:
- `EngineeringPlan`: The root entity. Holds metadata, provider details, and the `output`.
- `PlannerOutput`: Contains the summary, tasks, risks, assumptions, and validation strategy.
- `PlanTask`: Defines an individual action (e.g. `ANALYSIS`, `IMPLEMENTATION`) and its dependencies.

Plans are persisted as JSON in the database but pass through strict Pydantic models at runtime.
