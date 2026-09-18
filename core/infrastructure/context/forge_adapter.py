from core.domain.context.interfaces import ForgeContextProvider, ForgeContext
from core.domain.missions.entities import Mission

class StubForgeContextProvider(ForgeContextProvider):
    async def get_context(self, repository_id: str, mission: Mission) -> ForgeContext:
        # Currently a stub as Forge APIs are not explicitly integrated yet
        return ForgeContext(
            memories=["Stub memory: ensure proper error handling"],
            architecture_notes=["Stub note: FastApi backend with Postgres"]
        )
