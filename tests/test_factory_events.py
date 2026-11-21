"""Five contract tests for the event-driven factory; external writes are simulated."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from agent_kanban import services
from agent_kanban.auth import generate_token, hash_token
from agent_kanban.config import get_settings
from agent_kanban.models import AgentProject, Comment, Project, Task, TaskStatus, Token
from agent_kanban.routes.task_packages import package_paths
from agent_kanban.schemas import SubmitReview
from tests.test_factory_sequential import archive, factory_pg as _factory_pg, make_coordinator, start

factory_pg = _factory_pg


async def token_for(session, actor):
    token = generate_token()
    session.add(
        Token(
            agent_name=actor,
            token_hash=hash_token(token),
            token_prefix=token[:8],
            created_by_user_id=1,
        )
    )
    await session.commit()
    return {"Authorization": "Bearer " + token}


async def research_card(session, monkeypatch, tmp_path, factory_pg):
    c = await make_coordinator(session, monkeypatch, tmp_path, factory_pg)
    p = await c.advance(await start(c, factory_pg))
    task = await session.get(Task, int(p["brio_task_id"]))
    with patch("agent_kanban.factory_schedule.slot_open", return_value=True):
        assert (await services.claim_task(session, task.id, "brio", enforce_grant=True)).ok
    return c, p, task


async def test_submit_triggers_immediate_transition(
    session, authed_client, monkeypatch, tmp_path, factory_pg
):
    c, p, task = await research_card(session, monkeypatch, tmp_path, factory_pg)
    _, result = package_paths(task)
    result.write_bytes(
        archive({"hallazgos.md": "Evidence", "fuentes.json": "[]", "propuesta_mvp.md": "Scope"})
    )
    headers = await token_for(session, "brio")
    authed_client.cookies.clear()
    monkeypatch.setenv("FACTORY_SUPABASE_SECRET_KEY", "test-only")
    get_settings.cache_clear()
    monkeypatch.setattr("agent_kanban.factory_coordinator.process_event", c.event)
    try:
        response = await authed_client.post(
            f"/api/tasks/{task.id}/submit", headers=headers, json={"summary_of_work": "Done"}
        )
        assert response.status_code == 200
        await session.refresh(task)
        assert task.status == TaskStatus.DONE
        pipeline = await factory_pg.fetchrow(
            "SELECT stage,evaluation_task_id FROM opportunity_pipelines WHERE event_id=$1",
            p["event_id"],
        )
        assert pipeline["stage"] == "EVALUATING" and pipeline["evaluation_task_id"]
    finally:
        get_settings.cache_clear()
        await c.client.aclose()


async def test_existing_claim_can_deliver_outside_window(
    session, authed_client, monkeypatch, tmp_path, factory_pg
):
    c, p, task = await research_card(session, monkeypatch, tmp_path, factory_pg)
    headers = await token_for(session, "brio")
    authed_client.cookies.clear()
    try:
        with patch("agent_kanban.factory_schedule.slot_open", return_value=False):
            assert (
                await authed_client.post(
                    f"/api/tasks/{task.id}/heartbeat",
                    headers=headers,
                    json={"notes": "Still working after hours"},
                )
            ).status_code == 200
            assert (
                await authed_client.post(
                    f"/api/tasks/{task.id}/comments",
                    headers=headers,
                    json={"author": "brio", "content": "Progress"},
                )
            ).status_code == 201
            assert (
                await authed_client.put(
                    f"/api/tasks/{task.id}/package/result",
                    headers={**headers, "Content-Type": "application/zip"},
                    content=archive({"hallazgos.md": "Evidence"}),
                )
            ).status_code == 201
            assert (
                await authed_client.post(
                    f"/api/tasks/{task.id}/submit",
                    headers=headers,
                    json={"summary_of_work": "Delivered outside claim window"},
                )
            ).status_code == 200
    finally:
        await c.client.aclose()


async def test_wip_one_atomic_for_codex_and_dot_across_projects(session, db_url):
    projects = [Project(name="One"), Project(name="Two")]
    session.add_all(projects)
    await session.flush()
    ids = {}
    for actor, step in (("codex", "mvp"), ("dot", "landing")):
        cards = [
            Task(
                title=actor,
                project_id=p.id,
                assigned_to=actor,
                status=TaskStatus.READY,
                metadata_payload={"factory_mode": "sequential", "factory_step": step},
            )
            for p in projects
        ]
        session.add_all(
            cards
            + [AgentProject(agent_name=actor, project_id=p.id, role="worker") for p in projects]
        )
        await session.flush()
        ids[actor] = [t.id for t in cards]
    await session.commit()
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def claim(actor, task_id):
        async with factory() as s:
            return await services.claim_task(s, task_id, actor, enforce_grant=True)

    try:
        with patch("agent_kanban.factory_schedule.slot_open", return_value=True):
            for actor in ids:
                results = await asyncio.gather(*(claim(actor, task_id) for task_id in ids[actor]))
                assert sum(r.ok for r in results) == 1
                assert "WIP=1" in next(r.reason for r in results if not r.ok)
    finally:
        await engine.dispose()


async def test_invalid_result_returns_to_work_then_blocks(
    session, authed_client, monkeypatch, tmp_path, factory_pg
):
    c, p, task = await research_card(session, monkeypatch, tmp_path, factory_pg)
    _, result = package_paths(task)
    result.write_bytes(archive({"wrong.md": "Missing research files"}))
    alert = AsyncMock()
    monkeypatch.setattr(c, "alert", alert)
    headers = await token_for(session, "brio")
    authed_client.cookies.clear()
    try:
        for attempt in (1, 2):
            await services.submit_for_review(
                session, task.id, "brio", SubmitReview(summary_of_work="Attempt")
            )
            await c.event(p["event_id"])
            await session.refresh(task)
            assert task.metadata_payload["validation_retries"] == attempt
            assert task.status == (TaskStatus.IN_PROGRESS if attempt == 1 else TaskStatus.BLOCKED)
            if attempt == 1:
                response = await authed_client.put(
                    f"/api/tasks/{task.id}/package/result",
                    headers={**headers, "Content-Type": "application/zip"},
                    content=archive({"still-wrong.md": "Corrected upload allowed"}),
                )
                assert response.status_code == 201
        comments = (
            (await session.execute(select(Comment).where(Comment.task_id == task.id)))
            .scalars()
            .all()
        )
        assert len(comments) == 2 and all("missing required files" in c.content for c in comments)
        alert.assert_awaited_once()
        with pytest.raises(ValueError, match="operator recovery"):
            await services.submit_for_review(
                session, task.id, "brio", SubmitReview(summary_of_work="Bypass")
            )
    finally:
        await c.client.aclose()


async def test_public_leads_cors_honeypot_and_private_project_filter(
    session, authed_client, monkeypatch
):
    session.add(Project(name="Factory"))
    await session.flush()
    session.add(AgentProject(agent_name="n8n-radares", project_id=1, role="orchestrator"))
    headers = await token_for(session, "n8n-radares")
    rows = []

    def request(req):
        if req.url.path.endswith("opportunity_pipelines"):
            return httpx.Response(200, json=[{"event_id": "event-1", "run_landing": True}])
        if req.method == "POST":
            rows.append({"id": "d8ebc59f-f88e-41eb-8c2d-877713a5b8f2", **json.loads(req.content)})
            return httpx.Response(201, json=[rows[-1]])
        assert req.url.params["event_id"].startswith("eq.")
        assert req.url.params["project_slug"].startswith("eq.")
        return httpx.Response(
            200,
            json=[
                r
                for r in rows
                if "eq." + r["event_id"] == req.url.params["event_id"]
                and "eq." + r["project_slug"] == req.url.params["project_slug"]
            ],
        )

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(
            base_url="https://test/rest/v1/", transport=httpx.MockTransport(request)
        ) as c:
            yield c

    monkeypatch.setattr("agent_kanban.routes.factory_leads.supabase_client", client)
    authed_client.cookies.clear()
    path = "/api/factory/leads"
    lead = {
        "event_id": "event-1",
        "project_slug": "event-1",
        "full_name": "Example",
        "contact": "example@example.com",
        "source_url": "https://example.com",
    }
    response = await authed_client.post(path, json=lead, headers={"Origin": "https://example.com"})
    assert response.status_code == 201 and response.json()["lead_id"] == rows[0]["id"]
    assert response.headers["access-control-allow-origin"] == "*"
    assert (
        await authed_client.post(path, json={**lead, "honeypot": "bot"})
    ).status_code == 201 and len(rows) == 1
    assert (await authed_client.post(path, json={**lead, "contact": ""})).status_code == 422
    assert (
        await authed_client.get(path, params={"event_id": "event-1", "project_slug": "event-1"})
    ).status_code == 401
    for event, expected in (("event-1", 1), ("event-2", 0)):
        response = await authed_client.get(
            path, params={"event_id": event, "project_slug": event}, headers=headers
        )
        assert response.status_code == 200 and len(response.json()) == expected
    assert (
        await authed_client.get(
            path, params={"event_id": "event-1", "project_slug": "other"}, headers=headers
        )
    ).json() == []
    preflight = await authed_client.options(
        path,
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert preflight.status_code == 200
