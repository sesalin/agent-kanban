"""Project grants for authenticated agents. Human sessions manage the board."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban.models import AgentProject, Task


class TaskNotFound(LookupError):
    pass


class ProjectAccessDenied(PermissionError):
    pass


def authorized_projects(agent: str, role: str = "observer"):
    query = select(AgentProject.project_id).where(
        AgentProject.agent_name == agent, AgentProject.can_read.is_(True)
    )
    if role == "worker":
        query = query.where(
            AgentProject.role.in_(("worker", "orchestrator")), AgentProject.can_claim.is_(True)
        )
    elif role == "orchestrator":
        query = query.where(AgentProject.role == role)
    return query


async def verify_permissions(
    session: AsyncSession, agent: str, project_id: int | None, role: str = "observer"
) -> bool:
    if project_id is None:
        return False
    query = authorized_projects(agent, role).where(AgentProject.project_id == project_id)
    return (await session.execute(query)).scalar_one_or_none() is not None


async def require_project(
    session: AsyncSession, agent: str, project_id: int | None, role: str = "observer"
) -> None:
    if not await verify_permissions(session, agent, project_id, role):
        raise ProjectAccessDenied(f"Agente {agent!r} no autorizado en el proyecto {project_id}")


async def require_task(
    session: AsyncSession, task_id: int, agent: str, role: str = "observer", *, lock: bool = False
) -> Task:
    task = await session.get(Task, task_id, with_for_update=lock, populate_existing=lock)
    if task is None:
        raise TaskNotFound(f"task {task_id} not found")
    await require_project(session, agent, task.project_id, role)
    return task
