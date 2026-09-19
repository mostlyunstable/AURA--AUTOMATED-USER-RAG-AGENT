import asyncio
import os
import tempfile
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.main import app, engine, session_factory
from core.domain.execution.enums import CommandStatus, EnvironmentStatus
from core.infrastructure.database.models import Base

DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura@localhost:5432/aura"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    test_engine = create_async_engine(DB_URL, echo=False, poolclass=pool.NullPool)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def temp_git_repo():
    with tempfile.TemporaryDirectory() as td:
        proc = await asyncio.create_subprocess_exec("git", "init", cwd=td)
        await proc.wait()

        # Initial commit needed to create worktrees
        with open(os.path.join(td, "README.md"), "w") as f:
            f.write("Init")

        proc = await asyncio.create_subprocess_exec("git", "add", ".", cwd=td)
        await proc.wait()
        
        proc = await asyncio.create_subprocess_exec("git", "config", "user.email", "test@test.com", cwd=td)
        await proc.wait()
        proc = await asyncio.create_subprocess_exec("git", "config", "user.name", "Test", cwd=td)
        await proc.wait()

        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", "init", cwd=td
        )
        await proc.wait()

        yield td


@pytest.mark.asyncio
async def test_execution_boundary(async_client, temp_git_repo):
    # 1. Create Mission and skip straight to APPROVED_FOR_EXECUTION
    payload = {
        "title": "Execution Test",
        "description": "Desc",
        "repository_id": temp_git_repo,
        "source": "test",
    }
    resp = await async_client.post("/missions", json=payload)
    mission_id = resp.json()["id"]

    # We can't jump directly, we must go PLANNING -> PLANNED -> APPROVE -> EXECUTING
    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNING"}
    )
    await async_client.post(
        f"/missions/{mission_id}/transition", json={"target_state": "PLANNED"}
    )
    await async_client.post(
        f"/missions/{mission_id}/approve", json={"approval_type": "EXECUTION"}
    )

    # 1.5 Create Task and TaskExecution
    # Wait, we can create via API or just simulate. We have an API for tasks?
    resp = await async_client.post(
        f"/missions/{mission_id}/tasks",
        json={
            "title": "Exec Task",
            "description": "Desc",
            "task_type": "IMPLEMENTATION",
        },
    )
    task_id = resp.json()["id"]

    # Actually AURA doesn't have a direct API to create `TaskExecution` yet!
    # I'll just insert it via the database directly.
    import uuid
    from datetime import datetime, timezone

    execution_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(
            text(
                "INSERT INTO task_executions (id, task_id, status, attempt_number, started_at, result_metadata) VALUES (:eid, :tid, 'PENDING', 1, :now, '{}')"
            ),
            {"eid": execution_id, "tid": task_id, "now": datetime.now(timezone.utc)},
        )

    resp = await async_client.post(
        f"/tasks/{task_id}/executions/{execution_id}/environment?mission_id={mission_id}&repository_id={temp_git_repo}"
    )

    assert resp.status_code == 200
    env = resp.json()
    assert env["status"] == "READY"
    assert env["worktree_path"] is not None

    env_id = env["id"]
    worktree_path = env["worktree_path"]

    # Verify worktree exists
    assert os.path.exists(worktree_path)
    assert os.path.exists(os.path.join(worktree_path, "README.md"))

    # 3. Execute Valid Command (echo)
    cmd_payload = {
        "executable": "echo",
        "arguments": ["hello AURA"],
        "working_directory": worktree_path,
        "timeout_seconds": 10,
    }
    resp = await async_client.post(f"/environments/{env_id}/execute", json=cmd_payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "SUCCEEDED"
    assert "hello AURA" in result["stdout"]

    # 4. Execute Denied Command (rm)
    cmd_payload["executable"] = "rm"
    resp = await async_client.post(f"/environments/{env_id}/execute", json=cmd_payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "REJECTED"
    assert "not allowed" in result["failure_reason"]

    # 5. Execute Command Outside Worktree
    cmd_payload["executable"] = "ls"
    cmd_payload["working_directory"] = "/tmp"
    resp = await async_client.post(f"/environments/{env_id}/execute", json=cmd_payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "REJECTED"
    assert "outside the allowed worktree" in result["failure_reason"]

    # 6. Test Secret Redaction
    os.environ["OPENAI_API_KEY"] = "sk-super-secret"
    cmd_payload["executable"] = "echo"
    cmd_payload["arguments"] = ["sk-super-secret"]
    cmd_payload["working_directory"] = worktree_path
    resp = await async_client.post(f"/environments/{env_id}/execute", json=cmd_payload)
    result = resp.json()
    assert result["status"] == "SUCCEEDED"
    assert "[REDACTED]" in result["stdout"]
    assert "sk-super-secret" not in result["stdout"]

    # 7. Cleanup Environment
    resp = await async_client.delete(f"/environments/{env_id}")
    assert resp.status_code == 200

    # Verify worktree deleted
    assert not os.path.exists(worktree_path)
