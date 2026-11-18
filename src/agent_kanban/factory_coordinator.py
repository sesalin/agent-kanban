"""Deterministic reconciliation invoked by n8n; no model calls or agent wakeups."""

import json
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from agent_kanban import services
from agent_kanban.config import get_settings
from agent_kanban.db import _engine_for
from agent_kanban.factory_files import ROOT, execute, inside, write_once
from agent_kanban.factory_schedule import ACTORS, local_now
from agent_kanban.models import Task, TaskStatus
from agent_kanban.routes.task_packages import package_paths
from agent_kanban.schemas import DispatchTask

SUPABASE = "https://uobeshcvmtawjxibciuy.supabase.co"
OWNER = "n8n-radares"
FILES = {
    "research": ("01_input", "paquete.zip", "02_research", "research.zip"),
    "evaluation": ("02_research", "research.zip", "03_specs", "decision.zip"),
    "mvp": ("03_specs", "mvp-input.zip", "04_mvp", "mvp.zip"),
    "prospection": ("03_specs", "prospection-input.zip", "05_prospects", "prospects.zip"),
    "landing": ("03_specs", "landing-input.zip", "06_landing", "landing.zip"),
    "final": ("07_release", "final-input.zip", "07_release", "close.zip"),
}
REQUIRED = {
    "research": {"hallazgos.md", "fuentes.json", "propuesta_mvp.md"},
    "prospection": {"leads.csv", "outreach_copies.md"},
}


class Branches(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_mvp: StrictBool
    run_prospection: StrictBool
    run_landing: StrictBool


class Specs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mvp_prompt: str = ""
    icp_prompt: str = ""
    landing_prompt: str = ""


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    brio_task_id: int = Field(gt=0)
    decision: Literal["GO", "NO_GO"]
    decision_notes: str = Field(min_length=1, max_length=16000)
    branches: Branches
    specs: Specs

    @model_validator(mode="after")
    def check_branches(self):
        flags = self.branches.model_dump()
        if self.decision == "NO_GO" and any(flags.values()):
            raise ValueError("NO_GO cannot enable branches")
        if self.decision == "GO" and not any(flags.values()):
            raise ValueError("GO needs an active branch")
        for branch, prompt in [
            ("mvp", "mvp_prompt"),
            ("prospection", "icp_prompt"),
            ("landing", "landing_prompt"),
        ]:
            if flags["run_" + branch] and not getattr(self.specs, prompt).strip():
                raise ValueError("Active branch requires a specification")
        return self


class FinalClose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    executive_summary: str = Field(min_length=1, max_length=16000)


def next_step(p):
    if p["stage"] == "RESEARCH":
        return "research"
    if p["stage"] == "EVALUATING":
        return "evaluation"
    if p["stage"] == "BUILDING":
        for branch in ("mvp", "prospection", "landing"):
            if p["run_" + branch] and p[branch + "_status"] != "DONE":
                return branch
    if p["stage"] == "FINAL_REVIEW":
        return "final"
    return None


def task_column(step):
    return "brio_task_id" if step == "research" else step + "_task_id"


def read_result(path, step):
    if path.is_symlink() or not is_zipfile(path):
        raise ValueError("Missing or invalid result ZIP")
    with ZipFile(path) as archive:
        if not archive.namelist() or len(archive.infolist()) > 2000:
            raise ValueError("Empty ZIP or excessive member count")
        if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError("ZIP uncompressed size exceeds 100 MiB")
        if archive.testzip() is not None:
            raise ValueError("ZIP checksum failed")
        if not REQUIRED.get(step, set()).issubset(archive.namelist()):
            raise ValueError("Result ZIP is missing required files")
        if step in ("evaluation", "final"):
            filename = "decision.json" if step == "evaluation" else "close.json"
            info = archive.getinfo(filename)
            if info.file_size > 128 * 1024:
                raise ValueError("Structured result exceeds 128 KiB")
            return json.loads(archive.read(info))
    return {}


def bundle_final(root, p):
    folder = inside(root, p["event_id"])
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            ZipInfo("decision.json"), json.dumps(p["specs_payload"], ensure_ascii=False)
        )
        for step in ("research", "mvp", "prospection", "landing"):
            if step != "research" and not p["run_" + step]:
                continue
            _, _, directory, filename = FILES[step]
            result = inside(root, f"{p['event_id']}/{directory}/{filename}")
            if result.is_symlink() or not is_zipfile(result):
                raise ValueError("Missing accepted result")
            archive.writestr(ZipInfo(filename), result.read_bytes())
    write_once(folder / "07_release/final-input.zip", data.getvalue())


class Coordinator:
    def __init__(self, session, client):
        self.session, self.client = session, client
        self.root = Path(get_settings().muse_packages_root)

    async def api(self, method, path, **kwargs):
        response = await self.client.request(method, "/rest/v1/" + path, **kwargs)
        if response.is_error:
            # Provider bodies can include submitted data; keep them out of API errors and logs.
            raise RuntimeError(f"Supabase request failed: HTTP {response.status_code}")
        return response.json() if response.content else None

    async def rpc(self, name, **payload):
        return await self.api("POST", "rpc/" + name, json=payload)

    async def error(self, event_id, error):
        message = str(error)[:500] if isinstance(error, ValueError) else type(error).__name__
        await self.api(
            "PATCH",
            "opportunity_pipelines",
            params={"event_id": "eq." + event_id, "factory_mode": "eq.sequential"},
            json={"last_error": message},
        )

    async def prepare_task(self, p, step):
        event = p["event_id"]
        if step in ("mvp", "prospection", "landing"):
            await run_in_threadpool(execute, "specs", p["specs_payload"], self.root)
        if step == "final":
            await run_in_threadpool(bundle_final, self.root, p)
        source, input_file, destination, output_file = FILES[step]
        metadata = {
            "event_id": event,
            "factory_mode": "sequential",
            "factory_step": step,
            "factory_dispatch_key": event + ":sequential:" + step,
            "muse_zip": {
                "path": event + "/" + source,
                "input_file": input_file,
                "output_path": event + "/" + destination,
                "output_file": output_file,
            },
        }
        instructions = {
            "research": "Investiga con fuentes verificables. research.zip debe contener hallazgos.md, fuentes.json y propuesta_mvp.md.",
            "evaluation": f"Evalúa research.zip y entrega decision.zip con decision.json según el contrato secuencial. event_id={event}; brio_task_id={p['brio_task_id']}.",
            "mvp": p["specs_payload"].get("specs", {}).get("mvp_prompt", ""),
            "prospection": p["specs_payload"].get("specs", {}).get("icp_prompt", "")
            + " Entrega prospects.zip con leads.csv y outreach_copies.md. No contactes prospectos.",
            "landing": p["specs_payload"].get("specs", {}).get("landing_prompt", ""),
            "final": f'Revisa los entregables del ZIP de entrada. Entrega close.zip con close.json: {{"event_id":"{event}","executive_summary":"resumen verificado"}}.',
        }
        task = await services.dispatch_task(
            self.session,
            OWNER,
            DispatchTask(
                project_id=1,
                title=f"[{step}] {p['title']}",
                assigned_to=ACTORS[step],
                metadata=metadata,
                description=instructions[step]
                + " Reclama, descarga el paquete, entrega el ZIP, envía a revisión y consulta la siguiente tarjeta propia dentro de tu ventana. n8n concilia por horario; no llames webhooks de fábrica.",
            ),
        )
        p = await self.rpc(
            "factory_seq_record_task", p_event_id=event, p_step=step, p_task_id=str(task.id)
        )
        return p

    async def advance(self, p):
        step = next_step(p)
        if step is None:
            return p
        task_id = p.get(task_column(step))
        if not task_id:
            return await self.prepare_task(p, step)
        task = await self.session.get(Task, int(task_id), populate_existing=True)
        if (
            task is None
            or task.project_id != 1
            or task.created_by != OWNER
            or task.assigned_to != ACTORS[step]
        ):
            raise ValueError("Pipeline task identity/project mismatch")
        expected_key = p["event_id"] + ":sequential:" + step
        if (
            task.metadata_payload.get("factory_dispatch_key") != expected_key
            or task.metadata_payload.get("factory_mode") != "sequential"
        ):
            raise ValueError("Pipeline task metadata mismatch")
        if task.status not in (TaskStatus.REVIEW, TaskStatus.DONE):
            return p
        if task.claimed_by != ACTORS[step]:
            raise ValueError("Result was not claimed by its assigned actor")
        _, result = package_paths(task)
        document = await run_in_threadpool(read_result, result, step)
        event = p["event_id"]
        payload = {"event_id": event}
        if step == "evaluation":
            payload = Decision.model_validate(document).model_dump()
            if payload["event_id"] != event or str(payload["brio_task_id"]) != str(
                p["brio_task_id"]
            ):
                raise ValueError("Decision does not match the research task")
        elif step == "final":
            payload = FinalClose.model_validate(document).model_dump()
            if payload["event_id"] != event or not payload["executive_summary"].strip():
                raise ValueError("Final summary/event mismatch")
            payload["bundle_path"] = str(ROOT / event) + "/"
            await run_in_threadpool(execute, "release", payload, self.root)
        elif step == "research":
            payload.update(
                brio_task_id=str(task.id),
                research_zip_path=event + "/02_research/research.zip",
                summary="Investigación entregada en la tarjeta " + str(task.id),
            )
        else:
            payload.update(
                branch=step, task_id=str(task.id), zip_path=str(result.relative_to(self.root))
            )
        if task.status == TaskStatus.REVIEW:
            await services.review_task(
                self.session,
                task.id,
                OWNER,
                "APPROVE",
                "Entrega validada por el coordinador secuencial.",
            )
        p = await self.rpc(
            "factory_seq_complete",
            p_event_id=event,
            p_step=step,
            p_task_id=str(task.id),
            p_payload=payload,
        )
        following = next_step(p)
        if following:
            p = await self.prepare_task(p, following)
        return p

    async def pipelines(self, active_only):
        rows = []
        while True:
            page = await self.api(
                "GET",
                "opportunity_pipelines",
                params={
                    "factory_mode": "eq.sequential",
                    **({"stage": "not.in.(DONE,REJECTED)"} if active_only else {}),
                    "order": "created_at.asc,event_id.asc",
                    "limit": "100",
                    "offset": str(len(rows)),
                },
            )
            rows.extend(page)
            if len(page) < 100:
                break
        return rows

    async def tick(self, now):
        minute = now.hour * 60 + now.minute
        if not 740 <= minute <= 1320:
            return {"status": "outside_window", "report": None}
        seeded = 0
        if minute < 900:
            for source in await self.rpc("factory_seq_candidates", p_limit=20):
                try:
                    await run_in_threadpool(execute, "input", source, self.root)
                    await self.rpc("factory_seq_start", p_payload=source)
                    await self.api(
                        "PATCH",
                        "factory_runtime",
                        params={"id": "eq.source:" + source["event_id"]},
                        json={"last_error": None, "updated_at": now.isoformat()},
                    )
                    seeded += 1
                except (ValueError, OSError, RuntimeError, TypeError, KeyError) as error:
                    # A bad source must not prevent other opportunities from being reconciled.
                    await self.api(
                        "POST",
                        "factory_runtime",
                        headers={"Prefer": "resolution=merge-duplicates"},
                        json={
                            "id": "source:" + source["event_id"],
                            "last_error": type(error).__name__,
                            "updated_at": now.isoformat(),
                        },
                    )
        pipelines = await self.pipelines(active_only=True)
        failures = []
        for p in pipelines:
            try:
                await self.advance(p)
            except (
                ValueError,
                KeyError,
                OSError,
                BadZipFile,
                RuntimeError,
                HTTPException,
            ) as error:
                await self.session.rollback()
                await self.error(p["event_id"], error)
                failures.append(p["event_id"])
        await self.api(
            "POST",
            "factory_runtime",
            headers={"Prefer": "resolution=merge-duplicates"},
            json={
                "id": "coordinator",
                "last_error": ",".join(failures) or None,
                "updated_at": now.isoformat(),
            },
        )
        if minute >= 1260:
            date = now.date().isoformat()
            existing = await self.api(
                "GET", "factory_daily_reports", params={"report_date": "eq." + date}
            )
            if not existing:
                rows = await self.pipelines(active_only=False)
                rows.sort(key=lambda row: row["updated_at"], reverse=True)
                counts = {
                    stage: sum(p["stage"] == stage for p in rows)
                    for stage in (
                        "RESEARCH",
                        "EVALUATING",
                        "BUILDING",
                        "FINAL_REVIEW",
                        "DONE",
                        "REJECTED",
                    )
                }
                source_errors = await self.api(
                    "GET",
                    "factory_runtime",
                    params={
                        "id": "like.source:*",
                        "last_error": "not.is.null",
                        "select": "id",
                    },
                )
                message = (
                    "Fábrica "
                    + date
                    + " (America/Mexico_City)\n"
                    + ", ".join(f"{k}: {v}" for k, v in counts.items())
                    + "\n"
                )
                message += f"Paquetes con incidencia de origen: {len(source_errors)}\n"
                for p in rows[:8]:
                    message += (
                        f"\n{p['event_id']}: {p['stage']}\n"
                        + (
                            p.get("final_summary")
                            or p.get("decision_notes")
                            or p.get("last_error")
                            or "Pendiente"
                        )[:260]
                        + "\n"
                    )
                message += "\nTablero: https://kk.okehc.com"
                await self.api(
                    "POST",
                    "factory_daily_reports",
                    headers={"Prefer": "resolution=ignore-duplicates"},
                    json={"report_date": date, "message": message[:3900]},
                )
        pending = (
            await self.api(
                "GET",
                "factory_daily_reports",
                params={"sent_at": "is.null", "order": "report_date.asc", "limit": "1"},
            )
            if minute >= 1260
            else []
        )
        return {
            "status": "ok",
            "seeded": seeded,
            "checked": len(pipelines),
            "failures": failures,
            "report": pending[0] if pending else None,
        }


def supabase_client():
    settings = get_settings()
    if settings.factory_supabase_url.rstrip("/") != SUPABASE:
        raise ValueError("Factory must use the radars-n8n database")
    key = settings.factory_supabase_secret_key.get_secret_value()
    if not key or not settings.muse_packages_root:
        raise ValueError("Factory is not configured")
    headers = {"apikey": key, "User-Agent": "Kanban-Factory/1.0"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    return httpx.AsyncClient(base_url=SUPABASE, headers=headers, timeout=20, follow_redirects=False)


async def reconcile(session):
    # A dedicated connection keeps the session lock across commits made by task services.
    async with _engine_for(get_settings().database_url).connect() as connection:
        acquired = await connection.scalar(text("SELECT pg_try_advisory_lock(7331001)"))
        if not acquired:
            return {"status": "already_running", "report": None}
        try:
            async with supabase_client() as client:
                return await Coordinator(session, client).tick(local_now())
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(7331001)"))
