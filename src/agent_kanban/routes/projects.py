"""REST routes for projects."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.auth import Principal, get_current_principal
from agent_kanban.db import get_session
from agent_kanban.models import Project
from agent_kanban.permissions import authorized_projects, require_project
from agent_kanban.schemas import ProjectCreate, ProjectRead

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    query = select(Project).order_by(Project.created_at)
    if principal.is_token:
        query = query.where(Project.id.in_(authorized_projects(principal.agent_name)))
    result = await session.execute(query)
    return list(result.scalars())


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    data: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_token:
        raise HTTPException(403, "project creation requires a user session")
    project = Project(**data.model_dump())
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    if principal.is_token:
        await require_project(session, principal.agent_name, project_id)
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project
