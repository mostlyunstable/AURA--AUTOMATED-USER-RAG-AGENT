# Context Model

Context is abstracted behind:
- `RepositoryContextProvider`: Provides repository structure, branches, etc.
- `ForgeContextProvider`: Provides architectural notes, engineering memories, etc.

Both are currently stubbed but defined as strict Protocols to prevent leaking API schemas into the Planner Agent.
