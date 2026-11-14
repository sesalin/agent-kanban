"""Bearer endpoints for the same orchestration operations exposed by MCP."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent_kanban import services
from agent_kanban.auth import Principal, get_current_principal
from agent_kanban.db import get_session
from agent_kanban.models import TaskStatus
from agent_kanban.schemas import (
    DispatchTask,
    Heartbeat,
    ReassignTask,
    ReviewTask,
    SubmitReview,
    TaskRead,
)

router = APIRouter(prefix="/api/tasks", tags=["orchestration"])
DB = Annotated[AsyncSession, Depends(get_session)]


async def token_agent(principal: Annotated[Principal, Depends(get_current_principal)]) -> str:
    if not principal.is_token:
        raise HTTPException(403, "agent Bearer token required")
    return principal.agent_name


Agent = Annotated[str, Depends(token_agent)]


@router.get("/available", response_model=list[TaskRead])
async def available(session: DB, agent: Agent, project_id: int | None = None):
    return await services.list_tasks(
        session, TaskStatus.READY, agent=agent, project_id=project_id, claimable=True
    )


@router.post("/dispatch", status_code=201, response_model=TaskRead)
async def dispatch(data: DispatchTask, session: DB, agent: Agent):
    try:
        return await services.dispatch_task(session, agent, data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/{task_id}/claim", response_model=TaskRead)
async def claim(task_id: int, session: DB, agent: Agent):
    result = await services.claim_task(session, task_id, agent, enforce_grant=True)
    if not result.ok:
        raise HTTPException(404 if result.reason == "task not found" else 409, result.reason)
    return result.task


@router.post("/{task_id}/heartbeat", response_model=TaskRead)
async def heartbeat(task_id: int, data: Heartbeat, session: DB, agent: Agent):
    try:
        return await services.heartbeat_and_progress(session, task_id, agent, data)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{task_id}/submit", response_model=TaskRead)
async def submit(task_id: int, data: SubmitReview, session: DB, agent: Agent):
    try:
        return await services.submit_for_review(session, task_id, agent, data)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{task_id}/review", response_model=TaskRead)
async def review(task_id: int, data: ReviewTask, session: DB, agent: Agent):
    try:
        return await services.review_task(session, task_id, agent, data.verdict, data.feedback)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{task_id}/reassign", response_model=TaskRead)
async def reassign(task_id: int, data: ReassignTask, session: DB, agent: Agent):
    try:
        return await services.reassign_stalled_task(session, task_id, agent, data.new_agent_name)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
