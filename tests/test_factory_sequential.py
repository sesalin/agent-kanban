import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from agent_kanban import services
from agent_kanban.config import get_settings
from agent_kanban.factory_coordinator import Coordinator, next_step, pending_steps
from agent_kanban.factory_schedule import ZONE, slot_open
from agent_kanban.models import AgentProject, Project, Task, TaskStatus
from agent_kanban.routes.task_packages import package_paths
from agent_kanban.schemas import SubmitReview


def archive(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return stream.getvalue()


@pytest_asyncio.fixture
async def factory_pg(db_url):
    conn = await asyncpg.connect(db_url.replace("postgresql+asyncpg:", "postgresql:"))
    for role in ("anon", "authenticated", "service_role"):
        await conn.execute(
            f"DO $$ BEGIN CREATE ROLE {role}; EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    for table in ("radar_gobierno_nl", "radar_compras_publicas", "radar_regulacion_federal"):
        await conn.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
            event_id text PRIMARY KEY,title text,package_status text,analysis_status text,
            muse_status text,package_path text,package_filename text,packaged_at timestamptz,
            muse_sent_at timestamptz,muse_completed_at timestamptz,muse_result_path text,
            muse_result_filename text,muse_result_summary text,review_status text,
            resolution text,resolution_notes text,resolved_at timestamptz)""")
    await conn.execute(
        Path("deploy/factory/supabase.sql").read_text()
        + Path("deploy/factory/transitions.sql").read_text()
    )
    await conn.execute(Path("deploy/factory/sequential.sql").read_text())
    await conn.execute(Path("deploy/factory/parallel.sql").read_text())
    await conn.execute(
        "TRUNCATE opportunity_pipelines,radar_gobierno_nl,radar_compras_publicas,radar_regulacion_federal,factory_daily_reports,factory_runtime CASCADE"
    )
    yield conn
    await conn.close()


async def make_coordinator(session, monkeypatch, tmp_path, factory_pg):
    monkeypatch.setenv("MUSE_PACKAGES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    project = Project(name="Factory")
    session.add(project)
    await session.flush()
    session.add_all(
        [
            AgentProject(
                agent_name=a,
                project_id=project.id,
                role="orchestrator" if a in ("n8n-radares", "bacha") else "worker",
                can_claim=True,
            )
            for a in ("n8n-radares", "brio", "bacha", "codex", "dot")
        ]
    )
    await session.commit()

    async def request(req):
        name = req.url.path.rsplit("/", 1)[-1]
        args = json.loads(req.content)
        allowed = {"factory_seq_start", "factory_seq_record_task", "factory_seq_complete"}
        assert name in allowed
        placeholders = ",".join(f"${i + 1}" for i in range(len(args)))
        values = [json.dumps(v) if isinstance(v, dict) else v for v in args.values()]
        result = await factory_pg.fetchval(
            f"SELECT row_to_json(public.{name}({placeholders}))", *values
        )
        return httpx.Response(200, json=json.loads(result))

    client = httpx.AsyncClient(base_url="https://test", transport=httpx.MockTransport(request))
    return Coordinator(session, client)


async def start(coordinator, conn, event="test-sequential"):
    source = {"event_id": event, "radar_table": "radar_gobierno_nl", "title": "Sequential test"}
    await conn.execute(
        "INSERT INTO radar_gobierno_nl(event_id,title,package_status,analysis_status,muse_status) VALUES($1,$2,'ready','completed','ready')",
        event,
        source["title"],
    )
    folder = coordinator.root / event / "01_input"
    folder.mkdir(parents=True)
    for directory in (
        "02_research",
        "03_specs",
        "04_mvp",
        "05_prospects",
        "06_landing",
        "07_release",
    ):
        (coordinator.root / event / directory).mkdir()
    (folder / "paquete.zip").write_bytes(archive({"input.md": "Research this"}))
    return await coordinator.rpc("factory_seq_start", p_payload=source)


async def test_sequential_cycle_cards_zip_and_retry(session, monkeypatch, tmp_path, factory_pg):
    c = await make_coordinator(session, monkeypatch, tmp_path, factory_pg)
    try:
        p = await start(c, factory_pg)
        p = await c.advance(p)
        first = int(p["brio_task_id"])
        assert (await c.advance(p))["brio_task_id"] == str(first)
        decision = {
            "event_id": p["event_id"],
            "brio_task_id": first,
            "decision": "GO",
            "decision_notes": "Evidence checked",
            "branches": {"run_mvp": True, "run_prospection": True, "run_landing": True},
            "specs": {
                "mvp_prompt": "Build MVP",
                "icp_prompt": "Find companies",
                "landing_prompt": "Build landing",
            },
        }
        files = {
            "research": {
                "hallazgos.md": "Evidence",
                "fuentes.json": "[]",
                "propuesta_mvp.md": "Proposal",
            },
            "evaluation": {"decision.json": json.dumps(decision)},
            "mvp": {"README.md": "MVP"},
            "prospection": {"leads.csv": "empresa\nAcme", "outreach_copies.md": "Copy"},
            "landing": {"README.md": "Landing", "index.html": "<h1>Landing</h1>"},
            "final": {
                "close.json": json.dumps(
                    {"event_id": p["event_id"], "executive_summary": "Verified complete"}
                )
            },
        }
        ids = []
        for step, actor in [
            ("research", "brio"),
            ("evaluation", "bacha"),
            ("landing", "dot"),
            ("prospection", "bacha"),
            ("mvp", "codex"),
            ("final", "bacha"),
        ]:
            assert step in pending_steps(p)
            if step == "landing":
                assert all(
                    p.get(branch + "_task_id") for branch in ("mvp", "prospection", "landing")
                )
                assert p["final_task_id"] is None
                assert (await c.advance(p))["landing_task_id"] == p["landing_task_id"]
                # All three can hold their claims together, before any branch delivers.
                with patch("agent_kanban.factory_schedule.slot_open", return_value=True):
                    for branch, owner in (
                        ("mvp", "codex"),
                        ("prospection", "bacha"),
                        ("landing", "dot"),
                    ):
                        claim = await services.claim_task(
                            session, int(p[branch + "_task_id"]), owner, enforce_grant=True
                        )
                        assert claim.ok
            col = "brio_task_id" if step == "research" else step + "_task_id"
            task = await session.get(Task, int(p[col]), populate_existing=True)
            ids.append(task.id)
            await session.refresh(task)
            if task.status != TaskStatus.IN_PROGRESS:
                with patch("agent_kanban.factory_schedule.slot_open", return_value=True):
                    assert (
                        await services.claim_task(session, task.id, actor, enforce_grant=True)
                    ).ok
            assert task.assigned_to == actor and task.claimed_by == actor
            source, result = package_paths(task)
            assert source.is_file()
            result.write_bytes(archive(files[step]))
            await services.submit_for_review(
                session, task.id, actor, SubmitReview(summary_of_work="Done")
            )
            p = await c.advance(p)
            await session.refresh(task)
            assert task.status == TaskStatus.DONE
        assert p["stage"] == "DONE"
        assert next_step(p) is None
        assert (await c.advance(p))["stage"] == "DONE"
        count = (await session.execute(select(Task.id))).scalars().all()
        assert set(count) == set(ids) and len(count) == 6
        assert (
            tmp_path / p["event_id"] / "07_release/resumen_ejecutivo.md"
        ).read_text() == "Verified complete"
    finally:
        await c.client.aclose()


async def test_sql_order_no_go_and_private_grants(session, monkeypatch, tmp_path, factory_pg):
    c = await make_coordinator(session, monkeypatch, tmp_path, factory_pg)
    try:
        p = await start(c, factory_pg, "test-no-go")
        with pytest.raises(asyncpg.RaiseError, match="Preceding step"):
            await c.rpc(
                "factory_seq_record_task",
                p_event_id=p["event_id"],
                p_step="landing",
                p_task_id="500",
            )
        assert not await factory_pg.fetchval(
            "SELECT has_function_privilege('anon','public.factory_seq_complete(text,text,text,jsonb)','EXECUTE')"
        )
        assert not await factory_pg.fetchval(
            "SELECT has_table_privilege('anon','public.factory_daily_reports','SELECT')"
        )
        p = await c.rpc(
            "factory_seq_record_task", p_event_id=p["event_id"], p_step="research", p_task_id="100"
        )
        p = await c.rpc(
            "factory_seq_complete",
            p_event_id=p["event_id"],
            p_step="research",
            p_task_id="100",
            p_payload={
                "event_id": p["event_id"],
                "brio_task_id": "100",
                "research_zip_path": p["event_id"] + "/02_research/research.zip",
            },
        )
        await c.rpc(
            "factory_seq_record_task",
            p_event_id=p["event_id"],
            p_step="evaluation",
            p_task_id="101",
        )
        p = await c.rpc(
            "factory_seq_complete",
            p_event_id=p["event_id"],
            p_step="evaluation",
            p_task_id="101",
            p_payload={
                "event_id": p["event_id"],
                "brio_task_id": "100",
                "decision": "NO_GO",
                "decision_notes": "Not viable",
                "branches": {"run_mvp": False, "run_prospection": False, "run_landing": False},
                "specs": {},
            },
        )
        assert p["stage"] == "REJECTED" and next_step(p) is None
    finally:
        await c.client.aclose()


async def test_muse_exclusion_atomic_and_window(session, db_url, monkeypatch):
    project = Project(name="Factory")
    session.add(project)
    await session.flush()
    tasks = [
        Task(
            project_id=project.id,
            title=a,
            assigned_to=a,
            status=TaskStatus.READY,
            metadata_payload={"factory_mode": "sequential", "factory_step": s},
        )
        for a, s in [("brio", "research"), ("bacha", "evaluation")]
    ]
    session.add_all(
        tasks
        + [
            AgentProject(agent_name=a, project_id=project.id, role="worker")
            for a in ("brio", "bacha")
        ]
    )
    await session.commit()
    task_ids = [t.id for t in tasks]
    with patch("agent_kanban.factory_schedule.slot_open", return_value=False):
        rejected = await services.claim_task(session, task_ids[0], "brio", enforce_grant=True)
        assert not rejected.ok and "outside" in rejected.reason
    await session.rollback()
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def claim(task_id, actor):
        async with factory() as s:
            return await services.claim_task(s, task_id, actor, enforce_grant=True)

    import asyncio

    try:
        with patch("agent_kanban.factory_schedule.slot_open", return_value=True):
            outcomes = await asyncio.gather(claim(task_ids[0], "brio"), claim(task_ids[1], "bacha"))
        assert sum(o.ok for o in outcomes) == 1
        assert "Muse busy" in next(o.reason for o in outcomes if not o.ok)
    finally:
        await engine.dispose()
    for step, start, end in [
        ("research", 12 * 60 + 30, 15 * 60),
        ("evaluation", 15 * 60, 16 * 60),
        ("mvp", 16 * 60, 18 * 60),
        ("prospection", 16 * 60, 18 * 60),
        ("landing", 16 * 60, 18 * 60),
        ("final", 19 * 60, 19 * 60 + 30),
    ]:

        def at(minute):
            return datetime(2026, 11, 18, minute // 60, minute % 60, tzinfo=ZONE)

        assert not slot_open(step, at(start - 1))
        assert slot_open(step, at(start))
        assert not slot_open(step, at(end))


def test_codex_launcher_does_not_start_model_for_empty_queue(monkeypatch, tmp_path, capsys):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("factory_launcher", "deploy/factory/run-codex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CODEX_KANBAN_TOKEN", "test-codex-token")
    monkeypatch.setattr(sys, "argv", ["run-codex.py", "--check"])
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(module, "pending", lambda token: [])

    def unexpected(*args, **kwargs):
        raise AssertionError("An empty/check-only queue must not invoke a model")

    monkeypatch.setattr(module.subprocess, "run", unexpected)
    module.main()
    assert json.loads(capsys.readouterr().out)["ready_task_ids"] == []


async def test_daily_report_persists_once_and_outside_window_does_nothing(
    session, monkeypatch, tmp_path
):
    monkeypatch.setenv("MUSE_PACKAGES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    reports = []
    requests = []

    async def request(req):
        requests.append((req.method, req.url.path))
        table = req.url.path.rsplit("/", 1)[-1]
        if table == "opportunity_pipelines":
            return httpx.Response(200, json=[])
        if table == "factory_runtime":
            return httpx.Response(200, json=[])
        assert table == "factory_daily_reports"
        if req.method == "POST":
            reports.append(json.loads(req.content))
            return httpx.Response(201)
        return httpx.Response(200, json=reports)

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(request)
    ) as client:
        c = Coordinator(session, client)
        assert (await c.tick(datetime(2026, 11, 18, 12, 15, tzinfo=ZONE)))[
            "status"
        ] == "outside_window"
        assert requests == []
        for _ in range(2):
            response = await c.tick(datetime(2026, 11, 18, 19, 30, tzinfo=ZONE))
            assert response["report"]["report_date"] == "2026-11-18"
        assert len(reports) == 1
        assert "RESEARCH: 0" in reports[0]["message"]
        assert "Paquetes con incidencia de origen: 0" in reports[0]["message"]


async def test_bad_source_does_not_block_available_package(session, monkeypatch, tmp_path):
    monkeypatch.setenv("MUSE_PACKAGES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    source = tmp_path / "original"
    source.mkdir()
    (source / "source.zip").write_bytes(archive({"input.md": "Input"}))
    candidates = [
        {"event_id": "bad-source", "package_path": None, "package_filename": "source.zip"},
        {"event_id": "good-source", "package_path": str(source), "package_filename": "source.zip"},
    ]
    issues = []

    async def request(req):
        name = req.url.path.rsplit("/", 1)[-1]
        if name == "factory_seq_candidates":
            return httpx.Response(200, json=candidates)
        if name == "factory_seq_start":
            return httpx.Response(200, json={"event_id": "good-source"})
        if name == "opportunity_pipelines":
            return httpx.Response(200, json=[])
        assert name == "factory_runtime"
        if req.method == "POST":
            issues.append(json.loads(req.content))
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(request)
    ) as client:
        result = await Coordinator(session, client).tick(
            datetime(2026, 11, 18, 12, 20, tzinfo=ZONE)
        )
    assert result["seeded"] == 1
    assert any(issue["id"] == "source:bad-source" for issue in issues)
    assert (tmp_path / "good-source/01_input/paquete.zip").read_bytes() == (
        source / "source.zip"
    ).read_bytes()
