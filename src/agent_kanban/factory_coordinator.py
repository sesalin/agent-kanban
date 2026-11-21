"""Deterministic reconciliation invoked by n8n; no model calls or agent wakeups."""

import asyncio
import json
import logging
from io import BytesIO
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile, ZipFile, ZipInfo, is_zipfile

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from agent_kanban import services
from agent_kanban.config import get_settings
from agent_kanban.db import AsyncSessionLocal, _engine_for
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


def pending_steps(p):
    if p["stage"] == "BUILDING":
        return [
            branch
            for branch in ("mvp", "prospection", "landing")
            if p["run_" + branch] and p[branch + "_status"] != "DONE"
        ]
    step = next_step(p)
    return [step] if step else []


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
        self.root = Path(get_settings().muse_packages_root or ROOT)

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
        try:
            task = await services.dispatch_task(
                self.session,
                OWNER,
                DispatchTask(
                    project_id=1,
                    title=f"[{step}] {p['title']}",
                    assigned_to=ACTORS[step],
                    metadata=metadata,
                    description=instructions[step]
                    + " Reclama, descarga el paquete, entrega el ZIP, envía a revisión y consulta la siguiente tarjeta propia dentro de tu ventana. La entrega dispara validación automática. La ventana solo limita nuevos reclamos: continúa, publica avances y entrega fuera de horario. Una tarjeta activa a la vez; no llames webhooks de fábrica.",
                ),
            )
        except services.DailyMVPQuotaReached as error:
            logging.getLogger(__name__).warning("%s: %s", event, error)
            await self.api(
                "POST",
                "factory_runtime",
                headers={"Prefer": "resolution=merge-duplicates"},
                json={
                    "id": "quota:" + event,
                    "last_error": str(error),
                    "updated_at": local_now().isoformat(),
                },
            )
            return p
        p = await self.rpc(
            "factory_seq_record_task", p_event_id=event, p_step=step, p_task_id=str(task.id)
        )
        return p

    async def advance(self, p):
        for step in pending_steps(p):
            p = await self.advance_step(p, step)
        return p

    async def advance_step(self, p, step):
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
        try:
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
        except (ValueError, KeyError, OSError, BadZipFile, ValidationError, HTTPException) as error:
            if task.status != TaskStatus.REVIEW:
                raise
            await self.reject_result(task, error)
            return p
        if step == "final":
            await run_in_threadpool(execute, "release", payload, self.root)
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
        for following in pending_steps(p):
            if not p.get(task_column(following)):
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

    async def reject_result(self, task, error):
        message = f"{type(error).__name__}: {error}"
        # Keep validation errors useful without echoing entire JSON inputs or credentials.
        if isinstance(error, ValidationError):
            message = json.dumps(error.errors(include_input=False, include_url=False), default=str)
        await services.review_task(
            self.session, task.id, OWNER, "REJECT", message, validation_failure=True
        )
        if task.status == TaskStatus.BLOCKED:
            await self.alert(
                task.metadata_payload["event_id"],
                f"Tarjeta #{task.id} bloqueada tras {task.metadata_payload['validation_retries']} validaciones: {message}",
            )

    async def alert(self, event_id, message):
        try:
            await telegram_push({"type": "alert", "event_id": event_id, "message": message[:3900]})
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            logging.getLogger(__name__).error(
                "Telegram alert failed for %s: %s", event_id, type(error).__name__
            )
            await self.api(
                "POST",
                "factory_runtime",
                headers={"Prefer": "resolution=merge-duplicates"},
                json={
                    "id": "alert:" + event_id,
                    "last_error": str(error)[:500],
                    "updated_at": local_now().isoformat(),
                },
            )

    async def event(self, event_id):
        # A session advisory lock survives the commits made by the task services.
        async with _engine_for(get_settings().database_url).connect() as connection:
            await connection.execute(
                text("SELECT pg_advisory_lock(hashtextextended(:event, 7331005))"),
                {"event": event_id},
            )
            try:
                rows = await self.api(
                    "GET",
                    "opportunity_pipelines",
                    params={"event_id": "eq." + event_id, "factory_mode": "eq.sequential"},
                )
                if not rows or rows[0]["stage"] in ("DONE", "REJECTED"):
                    return
                try:
                    await self.advance(rows[0])
                except (
                    ValueError,
                    KeyError,
                    OSError,
                    BadZipFile,
                    RuntimeError,
                    HTTPException,
                    httpx.HTTPError,
                ) as error:
                    await self.session.rollback()
                    await self.error(event_id, error)
                    await self.alert(
                        event_id, f"Fallo de fábrica {event_id}: {type(error).__name__}: {error}"
                    )
                    raise
            finally:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:event, 7331005))"),
                    {"event": event_id},
                )

    async def admit(self, now):
        seeded, failures = 0, []
        # Admission is explicit; it is also allowed when manually invoked after 10:30.
        while candidates := await self.rpc("factory_seq_candidates", p_limit=50):
            for source in candidates:
                event = source["event_id"]
                try:
                    await run_in_threadpool(execute, "input", source, self.root)
                    await self.rpc("factory_seq_start", p_payload=source)
                    await self.event(event)
                    await self.api(
                        "PATCH",
                        "factory_runtime",
                        params={"id": "eq.source:" + event},
                        json={"last_error": None, "updated_at": now.isoformat()},
                    )
                    seeded += 1
                except (
                    ValueError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    KeyError,
                    httpx.HTTPError,
                ) as error:
                    await self.session.rollback()
                    failures.append(event)
                    await self.api(
                        "POST",
                        "factory_runtime",
                        headers={"Prefer": "resolution=merge-duplicates"},
                        json={
                            "id": "source:" + event,
                            "last_error": f"{event}: {type(error).__name__}: {error}",
                            "updated_at": now.isoformat(),
                        },
                    )
            if len(candidates) < 50:
                break
        return {"seeded": seeded, "failures": failures}

    async def tick(self, now):
        pipelines = await self.pipelines(active_only=True)
        failures = []
        for p in pipelines:
            try:
                await self.event(p["event_id"])
            except (
                ValueError,
                KeyError,
                OSError,
                BadZipFile,
                RuntimeError,
                HTTPException,
                httpx.HTTPError,
            ):
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
        return {"status": "ok", "checked": len(pipelines), "failures": failures}

    async def daily_report(self, now):
        date = now.date().isoformat()
        existing = await self.api(
            "GET", "factory_daily_reports", params={"report_date": "eq." + date}
        )
        if existing and existing[0].get("sent_at"):
            return {"status": "already_sent", "report_date": date}
        if existing:
            message = existing[0]["message"]
        else:
            rows = await self.pipelines(active_only=False)
            rows.sort(key=lambda row: row["updated_at"], reverse=True)
            stages = ("RESEARCH", "EVALUATING", "BUILDING", "FINAL_REVIEW", "DONE", "REJECTED")
            counts = ", ".join(
                f"{stage}: {sum(p['stage'] == stage for p in rows)}" for stage in stages
            )
            source_errors = await self.api(
                "GET",
                "factory_runtime",
                params={"id": "like.source:*", "last_error": "not.is.null", "select": "id"},
            )
            message = f"Fábrica {date} (America/Mexico_City)\n{counts}\nPaquetes con incidencia de origen: {len(source_errors)}\n"
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
            message = (message + "\nTablero: https://kk.okehc.com")[:3900]
            await self.api(
                "POST",
                "factory_daily_reports",
                headers={"Prefer": "resolution=ignore-duplicates"},
                json={"report_date": date, "message": message},
            )
        receipt = await telegram_push(
            {"type": "daily_report", "report_date": date, "message": message}
        )
        await self.api(
            "PATCH",
            "factory_daily_reports",
            params={"report_date": "eq." + date, "sent_at": "is.null"},
            json={
                "sent_at": now.isoformat(),
                "telegram_message_id": receipt["telegram_message_id"],
            },
        )
        return {"status": "sent", "report_date": date, **receipt}


async def telegram_push(payload):
    settings = get_settings()
    secret = settings.factory_webhook_secret.get_secret_value()
    if not secret:
        raise RuntimeError("FACTORY_WEBHOOK_SECRET is required for Telegram push")
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.post(
            settings.n8n_telegram_webhook_url, headers={"Authorization": secret}, json=payload
        )
    if response.status_code != 200:
        raise RuntimeError(f"Telegram webhook returned HTTP {response.status_code}")
    receipt = response.json()
    message_id = receipt.get("telegram_message_id")
    if receipt.get("ok") is not True or type(message_id) is not int or message_id <= 0:
        raise ValueError("Telegram webhook did not confirm a message ID")
    return receipt


_background_events = set()


def schedule_event(event_id, background_tasks=None):
    if not get_settings().factory_supabase_secret_key.get_secret_value():
        return
    if background_tasks is not None:
        background_tasks.add_task(process_event, event_id)
    else:
        # MCP has no FastAPI response; run the same BackgroundTasks callable after commit.
        from fastapi import BackgroundTasks

        tasks = BackgroundTasks()
        tasks.add_task(process_event, event_id)
        job = asyncio.create_task(tasks())
        _background_events.add(job)
        job.add_done_callback(_background_events.discard)


async def process_event(event_id):
    try:
        async with AsyncSessionLocal() as session, supabase_client() as client:
            await Coordinator(session, client).event(event_id)
    except Exception:
        logging.getLogger(__name__).exception("Background factory event failed: %s", event_id)


def supabase_client():
    settings = get_settings()
    if settings.factory_supabase_url.rstrip("/") != SUPABASE:
        raise ValueError("Factory must use the radars-n8n database")
    key = settings.factory_supabase_secret_key.get_secret_value()
    if not key:
        raise ValueError("Factory is not configured")
    headers = {"apikey": key, "User-Agent": "Kanban-Factory/1.0"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    return httpx.AsyncClient(base_url=SUPABASE, headers=headers, timeout=20, follow_redirects=False)


async def reconcile(session, operation="tick"):
    # A dedicated connection keeps the session lock across commits made by task services.
    async with _engine_for(get_settings().database_url).connect() as connection:
        acquired = await connection.scalar(text("SELECT pg_try_advisory_lock(7331001)"))
        if not acquired:
            return {"status": "already_running", "report": None}
        try:
            async with supabase_client() as client:
                return await getattr(Coordinator(session, client), operation)(local_now())
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(7331001)"))
