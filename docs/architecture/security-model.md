# Security Model

Autonomous execution represents a high security risk (e.g., prompt injection, code exfiltration, malicious system access).

**Protections Implemented**:
- Centralized `ToolGateway` (Architecture placeholder).
- **NO AUTONOMOUS SHELL IS ENABLED**.
- Explicit capability lists per agent and mission policies.
- Secrets are explicitly decoupled from the domain context.
- Authorization boundaries will require human approval for transitions to protected states (`APPROVED_FOR_EXECUTION`, `MERGED`).
