# Mission Lifecycle

A Mission is an autonomous engineering objective governed by a strict state machine.

**Valid Transitions**:
- `CREATED -> PLANNING`
- `PLANNING -> PLANNED`
- `PLANNED -> APPROVED_FOR_EXECUTION`
- `APPROVED_FOR_EXECUTION -> EXECUTING`
- `EXECUTING -> VERIFYING / RECOVERING`
- `VERIFYING -> VERIFIED / RECOVERING`
- `VERIFIED -> PR_READY`
- `PR_READY -> AWAITING_HUMAN_APPROVAL`
- `AWAITING_HUMAN_APPROVAL -> MERGED`

State transitions are transactional and immutable append-only Events are logged alongside each transition to provide an audit log and facilitate AgentOps.
