from core.domain.llm.interfaces import LLMProvider, LLMRequest, LLMResponse
import json
import time

class FakeLLMProvider(LLMProvider):
    def __init__(self, mode: str = "valid"):
        # mode can be: valid, malformed, cyclic, excessive, timeout, error
        self.mode = mode

    async def generate(self, request: LLMRequest) -> LLMResponse:
        start = time.time()
        if self.mode == "timeout":
            raise TimeoutError("Provider timeout")
        if self.mode == "error":
            raise RuntimeError("Provider error")

        if self.mode == "malformed":
            content = "{ invalid json"
        elif self.mode == "cyclic":
            content = json.dumps({
                "summary": "Cyclic plan",
                "assumptions": [],
                "risks": [],
                "tasks": [
                    {"title": "Task A", "description": "A", "task_type": "ANALYSIS", "dependencies": ["Task B"]},
                    {"title": "Task B", "description": "B", "task_type": "ANALYSIS", "dependencies": ["Task A"]}
                ],
                "validation_strategy": {"approach": "test", "tests_required": False}
            })
        elif self.mode == "excessive":
            content = json.dumps({
                "summary": "Huge plan",
                "assumptions": [],
                "risks": [],
                "tasks": [
                    {"title": f"Task {i}", "description": "Desc", "task_type": "ANALYSIS"} for i in range(100)
                ],
                "validation_strategy": {"approach": "test", "tests_required": False}
            })
        else: # valid
            content = json.dumps({
                "summary": "Valid plan",
                "assumptions": [{"description": "Assume X"}],
                "risks": [{"description": "Risk Y", "mitigation": "Mitigate Y"}],
                "tasks": [
                    {"title": "Analysis", "description": "Do analysis", "task_type": "ANALYSIS", "dependencies": []},
                    {"title": "Implementation", "description": "Do implementation", "task_type": "IMPLEMENTATION", "dependencies": ["Analysis"]}
                ],
                "validation_strategy": {"approach": "Unit tests", "tests_required": True}
            })

        latency = (time.time() - start) * 1000
        return LLMResponse(
            content=content,
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=20,
            latency_ms=latency,
            request_id="fake-id",
            finish_reason="stop"
        )
