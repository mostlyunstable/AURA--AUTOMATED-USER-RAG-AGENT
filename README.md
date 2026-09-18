# AURA — Autonomous Engineering & Agent Runtime

A production-grade autonomous software-engineering orchestration platform.

## Requirements
* Python 3.12+
* Docker
* Docker Compose

## Setup
1. Clone repository
2. Create virtual environment:
   `python -m venv .venv`
3. Install dependencies:
   `source .venv/bin/activate && pip install -e ".[dev]"`
4. Copy environment variables:
   `cp .env.example .env`
5. Start PostgreSQL:
   `docker compose up -d db`
6. Run migrations:
   `alembic upgrade head`
7. Start API:
   `uvicorn apps.api.main:app --reload`
8. Run tests:
   `pytest tests/`
