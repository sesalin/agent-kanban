import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_kanban.auth import generate_token, hash_token
from agent_kanban.models import AgentProject, Project, Task, TaskStatus, Token, User
from agent_kanban.permissions import verify_permissions
from agent_kanban.schemas import DispatchTask, SubmitReview
from agent_kanban.services import (
    claim_task,
    dispatch_task,
    list_tasks,
    review_task,
    submit_for_review,
)


async def create_project(session, name):
    project = Project(name=name)
    session.add(project)
    await session.flush()
    return project


@pytest.mark.asyncio
async def test_factory_dispatch_retry_reuses_task(session):
    project = await create_project(session, "factory")
    session.add_all([
        AgentProject(agent_name="n8n-radares", project_id=project.id, role="orchestrator"),
        AgentProject(agent_name="brio", project_id=project.id),
    ])
    await session.commit()
    payload = DispatchTask(project_id=project.id, title="Research", assigned_to="brio",
                           metadata={"factory_dispatch_key": "event-1:research"})
    first = await dispatch_task(session, "n8n-radares", payload)
    retried = await dispatch_task(session, "n8n-radares", payload)
    assert first.id == retried.id
    changed = payload.model_copy(update={"assigned_to": "codex"})
    with pytest.raises(ValueError, match="already used"):
        await dispatch_task(session, "n8n-radares", changed)


@pytest.mark.asyncio
async def test_cross_project_isolation(session, authed_client):
    """El token de domify sólo puede listar y reclamar tareas de domify."""
    domify = await create_project(session, "domify")
    serviceplace = await create_project(session, "serviceplace")
    admin = await session.get(User, 1)
    token = generate_token()
    foreign_task = Task(
        project_id=serviceplace.id, title="Crear migración catalog", status=TaskStatus.READY
    )
    session.add_all(
        [
            AgentProject(agent_name="codex", project_id=domify.id),
            Token(
                agent_name="codex",
                token_hash=hash_token(token),
                token_prefix=token[:8],
                created_by_user_id=admin.id,
            ),
            foreign_task,
        ]
    )
    await session.commit()

    assert not await verify_permissions(session, "codex", serviceplace.id, "worker")
    assert await list_tasks(session, TaskStatus.READY, agent="codex", claimable=True) == []
    with pytest.raises(PermissionError, match="no autorizado"):
        await claim_task(session, foreign_task.id, "codex", enforce_grant=True)

    authed_client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    for path in (f"/api/tasks/{foreign_task.id}", f"/api/tasks/{foreign_task.id}/comments"):
        assert (await authed_client.get(path, headers=headers)).status_code == 403
    assert (
        await authed_client.post(f"/api/tasks/{foreign_task.id}/claim", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_atomic_claim_race_condition(session, db_url):
    """Dos conexiones simultáneas compiten por la misma tarea en PostgreSQL."""
    project = await create_project(session, "serviceplace")
    task = Task(project_id=project.id, title="Optimizar PL/pgSQL", status=TaskStatus.READY)
    agents = ("codex_1", "codex_2")
    session.add_all(
        [task, *(AgentProject(agent_name=agent, project_id=project.id) for agent in agents)]
    )
    await session.commit()

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def claim(agent):
        async with factory() as competing_session:
            return await claim_task(competing_session, task.id, agent, enforce_grant=True)

    try:
        results = await asyncio.gather(*(claim(agent) for agent in agents))
    finally:
        await engine.dispose()
    assert sum(result.ok for result in results) == 1
    (winner,) = (result.task for result in results if result.ok)
    await session.refresh(task)
    assert task.status == TaskStatus.IN_PROGRESS
    assert task.claimed_by == winner.claimed_by
    assert task.last_heartbeat_at is not None


@pytest.mark.asyncio
async def test_dependency_unblocking_cascade(session):
    """Sólo se desbloquea la hija cuando todas sus dependencias están completas."""
    project = await create_project(session, "serviceplace")
    orchestrator = "hermes_orchestrator"
    worker = "codex"
    session.add_all(
        [
            AgentProject(agent_name=orchestrator, project_id=project.id, role="orchestrator"),
            AgentProject(agent_name=worker, project_id=project.id),
        ]
    )
    await session.commit()

    with patch("agent_kanban.webhooks.notify_task_event", new_callable=AsyncMock) as notify:
        first = await dispatch_task(
            session, orchestrator, DispatchTask(project_id=project.id, title="Modelos")
        )
        second = await dispatch_task(
            session, orchestrator, DispatchTask(project_id=project.id, title="Servicios")
        )
        child = await dispatch_task(
            session,
            orchestrator,
            DispatchTask(
                project_id=project.id,
                title="Pruebas",
                dependencies=[first.id, second.id],
            ),
        )
        assert child.status == TaskStatus.BLOCKED
        for parent in (first, second):
            assert (await claim_task(session, parent.id, worker, enforce_grant=True)).ok
            await submit_for_review(
                session, parent.id, worker, SubmitReview(summary_of_work="Listo")
            )
            await review_task(session, parent.id, orchestrator, "APPROVE")
            await session.refresh(child)
            assert child.status == (TaskStatus.BLOCKED if parent is first else TaskStatus.READY)

        assert [call.args[2] for call in notify.await_args_list].count("TASK_UNBLOCKED") == 1
