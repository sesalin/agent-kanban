"""File preparation for n8n's factory orchestration, bounded to configured roots."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from agent_kanban.config import get_settings
from agent_kanban.factory_files import execute
from agent_kanban.permissions import require_project
from agent_kanban.routes.orchestration import DB, Agent

router = APIRouter(prefix="/api/factory", tags=["factory"])
Operation = Literal["input", "specs", "verify", "wakeup", "release"]


async def factory_agent(session: DB, agent: Agent):
    if agent != "n8n-radares":
        raise HTTPException(403, "factory operations require the n8n factory identity")
    await require_project(session, agent, 1, "orchestrator")
    return agent


FactoryAgent = Annotated[str, Depends(factory_agent)]


@router.post("/files/{operation}")
async def prepare_files(operation: Operation, payload: dict, session: DB, agent: FactoryAgent):
    settings = get_settings()
    if not settings.muse_packages_root:
        raise HTTPException(503, "Factory package root is not configured")
    try:
        return await run_in_threadpool(
            execute,
            operation,
            payload,
            Path(settings.muse_packages_root),
            Path(settings.factory_tasks_root) if settings.factory_tasks_root else None,
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        # Filesystem errors may include private host paths; keep them off the API.
        raise HTTPException(422, "Invalid factory payload or inaccessible package file") from error


@router.post("/reconcile")
async def reconcile_factory(session: DB, agent: FactoryAgent):
    from agent_kanban.factory_coordinator import reconcile

    try:
        return await reconcile(session)
    except ValueError as error:
        raise HTTPException(503, "Factory coordinator is not configured") from error


class Delivery(BaseModel):
    message_id: int = Field(gt=0)


@router.post("/reports/{report_date}/sent")
async def report_sent(report_date: date, delivery: Delivery, session: DB, agent: FactoryAgent):
    from agent_kanban.factory_coordinator import Coordinator, supabase_client

    async with supabase_client() as client:
        response = await Coordinator(session, client).api(
            "PATCH",
            "factory_daily_reports",
            params={"report_date": "eq." + report_date.isoformat(), "sent_at": "is.null"},
            headers={"Prefer": "return=representation"},
            json={
                "sent_at": datetime.now(UTC).isoformat(),
                "telegram_message_id": delivery.message_id,
            },
        )
    return {"marked": bool(response)}


class WorkflowFailure(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    execution_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/error")
async def workflow_failed(data: WorkflowFailure, session: DB, agent: FactoryAgent):
    from agent_kanban.factory_coordinator import Coordinator, supabase_client

    async with supabase_client() as client:
        await Coordinator(session, client).api(
            "POST",
            "factory_runtime",
            headers={"Prefer": "resolution=merge-duplicates"},
            json={
                "id": "n8n",
                "last_error": f"workflow={data.workflow_id}; execution={data.execution_id}",
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
    return {"recorded": True}
