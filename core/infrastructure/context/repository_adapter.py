from core.domain.context.interfaces import RepositoryContextProvider, RepositoryContext
from core.domain.missions.entities import Mission

class StubRepositoryContextProvider(RepositoryContextProvider):
    async def get_context(self, repository_id: str, mission: Mission) -> RepositoryContext:
        return RepositoryContext(
            repository_id=repository_id,
            default_branch="main",
            metadata={"type": "stubbed"}
        )
