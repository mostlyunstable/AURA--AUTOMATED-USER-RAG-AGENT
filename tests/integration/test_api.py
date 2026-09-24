import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import app, get_mission_service
from core.application.mission_service import MissionService
from core.infrastructure.database.repositories import SQLAlchemyUnitOfWork

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def async_client(migrated_engine):
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)

    async def override_get_mission_service():
        uow = SQLAlchemyUnitOfWork(session_factory)
        return MissionService(uow)

    app.dependency_overrides[get_mission_service] = override_get_mission_service

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_mission(async_client):
    payload = {
        "title": "API Test",
        "description": "Desc",
        "repository_id": "repo1",
        "source": "api",
    }
    response = await async_client.post("/missions", json=payload)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_missions(async_client):
    payload = {
        "title": "List Test",
        "description": "Desc",
        "repository_id": "repo-list",
        "source": "api",
    }
    response = await async_client.post("/missions", json=payload)
    assert response.status_code == 200

    response = await async_client.get("/missions")
    assert response.status_code == 200
    assert any(m["title"] == "List Test" for m in response.json())


@pytest.mark.asyncio
async def test_pull_request_scoping_and_merge_flow(async_client):
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import text

    async def make_verified_mission(title, repo):
        resp = await async_client.post(
            "/missions",
            json={
                "title": title,
                "description": "D",
                "repository_id": repo,
                "source": "api",
            },
        )
        assert resp.status_code == 200
        mid = resp.json()["id"]
        for state in ("PLANNING", "PLANNED"):
            resp = await async_client.post(
                f"/missions/{mid}/transition", json={"target_state": state}
            )
            assert resp.status_code == 200
        resp = await async_client.post(
            f"/missions/{mid}/approve", json={"approval_type": "EXECUTION"}
        )
        assert resp.status_code == 200
        for state in ("EXECUTING", "VERIFYING", "VERIFIED"):
            resp = await async_client.post(
                f"/missions/{mid}/transition", json={"target_state": state}
            )
            assert resp.status_code == 200, resp.text
        return mid

    async def make_task_execution(mission_id):
        resp = await async_client.post(
            f"/missions/{mission_id}/tasks",
            json={"title": "T", "description": "D", "task_type": "IMPLEMENTATION"},
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]
        execution_id = str(uuid.uuid4())
        engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
        try:
            async with engine.begin() as conn:
                # Create an agent for this mission
                agent_id = str(uuid.uuid4())
                await conn.execute(
                    text(
                        "INSERT INTO agents (id, name, agent_type, version, capabilities, status, created_at, updated_at) "
                        "VALUES (:id, 'test-agent', 'CODING_AGENT', '1.0', '[]', 'ACTIVE', :now, :now)"
                    ),
                    {"id": agent_id, "now": datetime.now(timezone.utc)},
                )
                await conn.execute(
                    text(
                        "INSERT INTO task_executions (id, task_id, status, attempt_number, started_at, result_metadata) "
                        "VALUES (:eid, :tid, 'SUCCEEDED', 1, :now, '{}')"
                    ),
                    {
                        "eid": execution_id,
                        "tid": task_id,
                        "now": datetime.now(timezone.utc),
                    },
                )
                # Add agent_run and passing verification result for this task execution
                agent_run_id = str(uuid.uuid4())
                await conn.execute(
                    text(
                        "INSERT INTO agent_runs (id, mission_id, task_id, task_execution_id, agent_id, status, iteration_count, tool_call_count, max_iterations, max_tool_calls, max_runtime_seconds, max_failed_actions, started_at, completed_at, failure_reason, final_result, created_at, updated_at) "
                        "VALUES (:id, :mid, :tid, :eid, :aid, 'COMPLETED', 0, 0, 50, 100, 1800, 5, :now, :now, NULL, NULL, :now, :now)"
                    ),
                    {
                        "id": agent_run_id,
                        "mid": mission_id,
                        "tid": task_id,
                        "eid": execution_id,
                        "aid": agent_id,
                        "now": datetime.now(timezone.utc),
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO verification_results (id, agent_run_id, task_execution_id, status, success, checks, failed_checks, warnings, changed_files, test_results, diff_summary, failure_reason, started_at, completed_at, created_at) "
                        "VALUES (:vid, :aid, :eid, 'PASSED', true, '[]', '[]', '[]', '[]', '{}', '', NULL, :now, :now, :now)"
                    ),
                    {
                        "vid": str(uuid.uuid4()),
                        "aid": agent_run_id,
                        "eid": execution_id,
                        "now": datetime.now(timezone.utc),
                    },
                )
        finally:
            await engine.dispose()
        return task_id, execution_id

    mission_a = await make_verified_mission("Mission A", "repo-a")
    _, exec_a = await make_task_execution(mission_a)
    mission_b = await make_verified_mission("Mission B", "repo-b")
    _, exec_b = await make_task_execution(mission_b)

    pr_payload = {
        "task_execution_id": str(uuid.uuid4()),
        "source_branch": "feature",
        "title": "Fix",
    }
    # Unknown execution -> 404
    resp = await async_client.post(f"/missions/{mission_a}/pr", json=pr_payload)
    assert resp.status_code == 404

    # Execution from another mission -> 403
    pr_payload["task_execution_id"] = exec_b
    resp = await async_client.post(f"/missions/{mission_a}/pr", json=pr_payload)
    assert resp.status_code == 403

    # Own execution -> 200
    pr_payload["task_execution_id"] = exec_a
    resp = await async_client.post(f"/missions/{mission_a}/pr", json=pr_payload)
    assert resp.status_code == 200, resp.text

    # Walk to merge approval and approve -> MERGED
    for state in ("PR_READY", "AWAITING_HUMAN_APPROVAL"):
        resp = await async_client.post(
            f"/missions/{mission_a}/transition", json={"target_state": state}
        )
        assert resp.status_code == 200, resp.text
    resp = await async_client.post(
        f"/missions/{mission_a}/merge", json={"approval_type": "MERGE"}
    )
    assert resp.status_code == 200
    resp = await async_client.post(
        f"/missions/{mission_a}/merge/approve", json={"approval_type": "MERGE"}
    )
    assert resp.status_code == 200
    resp = await async_client.get(f"/missions/{mission_a}")
    assert resp.json()["status"] == "MERGED"


@pytest.mark.asyncio
async def test_mission_flow(async_client):
    payload = {
        "title": "API Test 2",
        "description": "Desc 2",
        "repository_id": "repo2",
        "source": "api",
    }
    response = await async_client.post("/missions", json=payload)
    mission_id = response.json()["id"]

    response = await async_client.get(f"/missions/{mission_id}")
    assert response.status_code == 200

    response = await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )
    assert response.status_code == 200
