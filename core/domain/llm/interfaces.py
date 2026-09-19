from typing import Any, Dict, Optional, Protocol

from pydantic import BaseModel


class LLMRequest(BaseModel):
    provider: str
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.0
    max_tokens: int = 4096
    metadata: Dict[str, Any] = {}
    response_format: Optional[Any] = None


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    request_id: str
    finish_reason: str
    metadata: Dict[str, Any] = {}


class LLMProvider(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
