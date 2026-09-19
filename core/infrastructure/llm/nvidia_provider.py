import time

import httpx

from core.domain.llm.interfaces import LLMProvider, LLMRequest, LLMResponse


class NvidiaLLMProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://integrate.api.nvidia.com/v1"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.time()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_format": (
                {"type": "json_object"} if request.response_format else None
            ),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

        latency = (time.time() - start) * 1000
        content = data["choices"][0]["message"]["content"]

        return LLMResponse(
            content=content,
            provider="nvidia",
            model=request.model,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            latency_ms=latency,
            request_id=data.get("id", ""),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )
