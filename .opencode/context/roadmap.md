# AURA Roadmap

**LAST VERIFIED: 2026-09-21 / b05a9c9 (AURA-010)**

## Roadmap

### COMPLETED

| Phase | Description | Commit |
|-------|-------------|--------|
| **AURA-001** | Project skeleton + basic infrastructure | (initial) |
| **AURA-002** | Domain models (Mission, Task, Agent, Event) | (early) |
| **AURA-003** | Planner Agent + DAG scheduling | 0d6babccd4b5 |
| **AURA-004** | Execution boundary + sandbox + worktree | ec82cfa28661 |
| **AURA-005** | Coding Agent Runtime + LLM integration | d186a8709edf |
| **AURA-006** | Verification Engine + duplicate fixes | e8957405ae91 |
| **AURA-007** | PR Creation + Human Approval + Merge | 69bb449 / a6f4eeb |
| **AURA-008** | Worker Pool + Task Claiming (durable) | 37ee5f6cfaa9 / b15ee7ab0547 |
| **AURA-009** | Worker Orchestration + Real Execution | b05a9c9 |
| **AURA-010** | **GitHub Provider Integration** | *uncommitted* |

---

### IN PROGRESS

| Phase | Description | Target |
|-------|-------------|--------|
| **AURA-011** | Multi-Agent Orchestration | Next |
| **AURA-012** | Agent Recovery (bounded retries, failure classes) | After AURA-011 |

---

### NEXT (AURA-011: Multi-Agent Orchestration)

| Task | Description |
|------|-------------|
| `AgentCoordinator` | `core/application/agent_coordinator.py` |
| `AgentTask` / `AgentDependency` / `AgentMessage` | Domain entities in `core/domain/agents/` |
| Multi-agent DAG execution | Dependency resolution, parallel execution |
| Specialized agents | Debugger, Tester, SecurityReviewer, CodeReviewer |
| Agent message passing | Structured communication between agents |

---

### LATER (Post AURA-011)

| Phase | Description | Dependency |
|-------|-------------|------------|
| **AURA-012** | Agent Recovery (bounded retries, failure classes) | AURA-011 |
| **AURA-013** | Code Review Agent | AURA-011 |
| **AURA-014** | Security Review Agent | AURA-011 |
| **AURA-015** | Real Authentication/Authorization | — |
| **AURA-016** | Production Deployment (Docker, K8s, secrets) | — |
| **AURA-017** | Observability (tracing, correlation IDs) | — |
| **AURA-018** | Resource/Cost Control (token budgets, timeouts) | — |

---

### Milestone Map

```
AURA-001 to 010  →  FOUNDATION (complete)
      ↓
AURA-011          →  MULTI-AGENT ORCHESTRATION (next)
      ↓
AURA-012 to 014   →  REVIEWS + RECOVERY
      ↓
AURA-015 to 018   →  PRODUCTION READINESS
```
AURA-001 to 009  →  FOUNDATION (complete)
      ↓
AURA-010          →  GITHUB INTEGRATION (next)
      ↓
AURA-011 to 014   →  MULTI-AGENT + REVIEWS
      ↓
AURA-015 to 018   →  PRODUCTION READINESS
```