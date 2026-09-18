# LLM Provider Abstraction

AURA interacts with LLMs through the `LLMProvider` Protocol.

Providers implemented:
1. `FakeLLMProvider`: Deterministic provider for tests.
2. `NvidiaLLMProvider`: Standard adapter to connect to NVIDIA APIs.
