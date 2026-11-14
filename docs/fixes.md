Migración SQL Inicial (PostgreSQL 17)
Ejecuta esto en tu base de datos o agrégalo en tu migración de Alembic:

SQL
-- Tabla de vinculación de agentes con proyectos
CREATE TABLE IF NOT EXISTS agent_projects (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    project_id VARCHAR(100) NOT NULL,
    can_read BOOLEAN NOT NULL DEFAULT TRUE,
    can_claim BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    CONSTRAINT uq_agent_project UNIQUE (agent_name, project_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_projects_agent ON agent_projects (agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_projects_project ON agent_projects (project_id);

-- Asegurar índice en tareas para reclamos atómicos de alta concurrencia
CREATE INDEX IF NOT EXISTS idx_tasks_claim_lookup ON tasks (id, status, assigned_to);





1. models.py
Python
"""
Data models for agent-kanban.
Enhanced with project authorization and multi-agent isolation.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Token(SQLModel, table=True):
    __tablename__ = "tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True, unique=True)
    token_hash: str
    token_prefix: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentProject(SQLModel, table=True):
    """Permisos de agentes por proyecto."""
    __tablename__ = "agent_projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True)
    project_id: str = Field(index=True)
    can_read: bool = Field(default=True)
    can_claim: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: str = Field(primary_key=True)
    project_id: str = Field(index=True)
    title: str
    description: Optional[str] = None
    status: TaskStatus = Field(default=TaskStatus.BACKLOG, index=True)
    priority: int = Field(default=3)  # 1 (Urgent) a 5 (Low)

    assigned_to: Optional[str] = Field(default=None, index=True)
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Metadatos de Git (desacoplados de CLI local)
    git_branch: Optional[str] = None
    git_pr_url: Optional[str] = None
    git_commit_hash: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaskComment(SQLModel, table=True):
    __tablename__ = "task_comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    agent_name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskArtifact(SQLModel, table=True):
    __tablename__ = "task_artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    agent_name: str
    artifact_type: str  # log, diff, report, pr_link
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)







2. services.py
Python
"""
Core business logic and database interactions with atomic concurrency locks.
"""
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import select, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from models import Task, TaskStatus, TaskComment, TaskArtifact, AgentProject


class AuthorizationError(Exception):
    pass


class TaskConcurrencyError(Exception):
    pass


class TaskNotFoundError(Exception):
    pass


class KanbanService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------
    # Permisos & Autorización
    # -------------------------------------------------------------
    async def get_authorized_project_ids(self, agent_name: str, require_claim: bool = False) -> List[str]:
        """Obtiene la lista de project_id a los que el agente tiene acceso."""
        stmt = select(AgentProject.project_id).where(AgentProject.agent_name == agent_name)
        if require_claim:
            stmt = stmt.where(AgentProject.can_claim == True)
        else:
            stmt = stmt.where(AgentProject.can_read == True)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def verify_task_access(self, agent_name: str, task_id: str, require_claim: bool = False) -> Task:
        """Valida que la tarea exista y que el agente tenga permisos sobre su proyecto."""
        stmt = select(Task).where(Task.id == task_id)
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if not task:
            raise TaskNotFoundError(f"Task '{task_id}' no encontrada.")

        allowed_projects = await self.get_authorized_project_ids(agent_name, require_claim=require_claim)
        if task.project_id not in allowed_projects:
            raise AuthorizationError(
                f"El agente '{agent_name}' no tiene permisos para acceder al proyecto '{task.project_id}'."
            )
        return task

    # -------------------------------------------------------------
    # Gestión de Tareas
    # -------------------------------------------------------------
    async def list_available_tasks(self, agent_name: str, project_id: Optional[str] = None) -> List[Task]:
        """
        Lista tareas en estado READY que pertenezcan a los proyectos autorizados del agente.
        Asegura que tareas huérfanas de otros proyectos no sean visibles.
        """
        allowed_projects = await self.get_authorized_project_ids(agent_name, require_claim=True)
        if not allowed_projects:
            return []

        if project_id:
            if project_id not in allowed_projects:
                raise AuthorizationError(f"Sin acceso al proyecto '{project_id}'.")
            projects_filter = [project_id]
        else:
            projects_filter = allowed_projects

        stmt = (
            select(Task)
            .where(
                Task.project_id.in_(projects_filter),
                Task.status == TaskStatus.READY,
                or_(Task.assigned_to.is_(None), Task.assigned_to == agent_name)
            )
            .order_by(Task.priority.asc(), Task.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def claim_task(self, task_id: str, agent_name: str) -> Task:
        """
        Reclamo 100% atómico con candado transaccional.
        Evita race condition entre chequeo y asignación.
        """
        # 1. Verificar autorización por proyecto
        await self.verify_task_access(agent_name, task_id, require_claim=True)

        # 2. UPDATE atómico en base de datos
        now = datetime.utcnow()
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                Task.status == TaskStatus.READY,
                or_(Task.assigned_to.is_(None), Task.assigned_to == agent_name)
            )
            .values(
                status=TaskStatus.IN_PROGRESS,
                assigned_to=agent_name,
                claimed_at=now,
                updated_at=now
            )
            .execution_options(synchronize_session="fetch")
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        if result.rowcount == 0:
            # Falló: o ya la ganó otro agente, o cambió de estado en milisegundos
            task_check = (await self.session.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
            if not task_check:
                raise TaskNotFoundError(f"Task '{task_id}' no existe.")
            raise TaskConcurrencyError(
                f"No se pudo reclamar '{task_id}'. Estado actual: '{task_check.status}', asignado a: '{task_check.assigned_to}'."
            )

        # Recuperar la entidad actualizada
        return await self.verify_task_access(agent_name, task_id)

    async def update_task_progress(
        self,
        task_id: str,
        agent_name: str,
        status: TaskStatus,
        git_branch: Optional[str] = None,
        git_pr_url: Optional[str] = None,
        git_commit_hash: Optional[str] = None,
    ) -> Task:
        """Actualiza el progreso de una tarea asignada al agente."""
        task = await self.verify_task_access(agent_name, task_id, require_claim=True)
        if task.assigned_to != agent_name:
            raise AuthorizationError(f"La tarea '{task_id}' está asignada a '{task.assigned_to}', no a '{agent_name}'.")

        task.status = status
        task.updated_at = datetime.utcnow()
        if git_branch:
            task.git_branch = git_branch
        if git_pr_url:
            task.git_pr_url = git_pr_url
        if git_commit_hash:
            task.git_commit_hash = git_commit_hash

        if status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()

        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    # -------------------------------------------------------------
    # Comentarios y Artefactos (Audit Trail)
    # -------------------------------------------------------------
    async def add_comment(self, task_id: str, agent_name: str, content: str) -> TaskComment:
        await self.verify_task_access(agent_name, task_id, require_claim=False)
        comment = TaskComment(task_id=task_id, agent_name=agent_name, content=content)
        self.session.add(comment)
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    async def get_comments(self, task_id: str, agent_name: str) -> List[TaskComment]:
        """Asegura que un agente no lea comentarios de tareas fuera de sus proyectos."""
        await self.verify_task_access(agent_name, task_id, require_claim=False)
        stmt = (
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_artifact(self, task_id: str, agent_name: str, artifact_type: str, content: str) -> TaskArtifact:
        await self.verify_task_access(agent_name, task_id, require_claim=True)
        artifact = TaskArtifact(
            task_id=task_id,
            agent_name=agent_name,
            artifact_type=artifact_type,
            content=content
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def get_artifacts(self, task_id: str, agent_name: str) -> List[TaskArtifact]:
        await self.verify_task_access(agent_name, task_id, require_claim=False)
        stmt = (
            select(TaskArtifact)
            .where(TaskArtifact.task_id == task_id)
            .order_by(TaskArtifact.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())







3. mcp_server.py
Python
"""
MCP Server implementation exposing tools to agent workers.
Integrates authentication, multi-project RBAC, and decoupled Git reporting.
"""
import os
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP, Context
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from models import TaskStatus
from services import (
    KanbanService,
    AuthorizationError,
    TaskConcurrencyError,
    TaskNotFoundError
)

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/kanban")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

mcp = FastMCP("AgentKanbanServer")


def get_authenticated_agent(ctx: Context) -> str:
    """
    Extrae la identidad del agente autenticado desde el contexto del transporte MCP/HTTP.
    """
    if ctx and hasattr(ctx, "client_id") and ctx.client_id:
        return ctx.client_id

    # Fallback para desarrollo o headers personalizados
    headers = getattr(ctx, "headers", {}) if ctx else {}
    agent_name = headers.get("x-agent-name")
    if not agent_name:
        raise PermissionError("No se pudo identificar al agente. Falta token o cabecera de identidad válida.")
    return agent_name


# -----------------------------------------------------------------
# MCP Tools
# -----------------------------------------------------------------

@mcp.tool()
async def list_available_tasks(project_id: Optional[str] = None, ctx: Context = None) -> List[Dict[str, Any]]:
    """
    Lista tareas listas para trabajar en los proyectos autorizados para este agente.
    """
    agent_name = get_authenticated_agent(ctx)
    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            tasks = await service.list_available_tasks(agent_name, project_id=project_id)
            return [
                {
                    "id": t.id,
                    "project_id": t.project_id,
                    "title": t.title,
                    "description": t.description,
                    "priority": t.priority,
                    "status": t.status.value,
                    "assigned_to": t.assigned_to,
                }
                for t in tasks
            ]
        except AuthorizationError as e:
            return [{"error": str(e)}]


@mcp.tool()
async def claim_task(task_id: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Reclama una tarea de forma atómica. Falla si ya fue tomada o no hay permisos.
    """
    agent_name = get_authenticated_agent(ctx)
    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            task = await service.claim_task(task_id, agent_name)
            return {
                "success": True,
                "message": f"Tarea '{task.id}' asignada exitosamente a '{agent_name}'.",
                "task": {
                    "id": task.id,
                    "project_id": task.project_id,
                    "title": task.title,
                    "status": task.status.value,
                }
            }
        except (AuthorizationError, TaskConcurrencyError, TaskNotFoundError) as e:
            return {"success": False, "error": str(e)}


@mcp.tool()
async def update_task_progress(
    task_id: str,
    status: str,
    git_branch: Optional[str] = None,
    git_pr_url: Optional[str] = None,
    git_commit_hash: Optional[str] = None,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Actualiza el estado de una tarea y reporta evidencias de Git vía parámetros.
    """
    agent_name = get_authenticated_agent(ctx)
    try:
        new_status = TaskStatus(status)
    except ValueError:
        return {"success": False, "error": f"Estado inválido: '{status}'. Válidos: {[s.value for s in TaskStatus]}"}

    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            task = await service.update_task_progress(
                task_id=task_id,
                agent_name=agent_name,
                status=new_status,
                git_branch=git_branch,
                git_pr_url=git_pr_url,
                git_commit_hash=git_commit_hash
            )
            return {
                "success": True,
                "task_id": task.id,
                "status": task.status.value,
                "updated_at": task.updated_at.isoformat()
            }
        except (AuthorizationError, TaskNotFoundError) as e:
            return {"success": False, "error": str(e)}


@mcp.tool()
async def add_task_comment(task_id: str, content: str, ctx: Context = None) -> Dict[str, Any]:
    """Agrega un comentario o nota de avance a una tarea."""
    agent_name = get_authenticated_agent(ctx)
    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            comment = await service.add_comment(task_id, agent_name, content)
            return {"success": True, "comment_id": comment.id}
        except (AuthorizationError, TaskNotFoundError) as e:
            return {"success": False, "error": str(e)}


@mcp.tool()
async def get_task_comments(task_id: str, ctx: Context = None) -> List[Dict[str, Any]]:
    """Consulta el historial de comentarios de una tarea con validación de aislamiento de proyecto."""
    agent_name = get_authenticated_agent(ctx)
    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            comments = await service.get_comments(task_id, agent_name)
            return [
                {
                    "id": c.id,
                    "agent_name": c.agent_name,
                    "content": c.content,
                    "created_at": c.created_at.isoformat()
                }
                for c in comments
            ]
        except (AuthorizationError, TaskNotFoundError) as e:
            return [{"error": str(e)}]


@mcp.tool()
async def attach_task_artifact(task_id: str, artifact_type: str, content: str, ctx: Context = None) -> Dict[str, Any]:
    """
    Registra evidencias o diffs generados por el agente (evita correr Git CLI local en el host).
    """
    agent_name = get_authenticated_agent(ctx)
    async with async_session_factory() as session:
        service = KanbanService(session)
        try:
            artifact = await service.add_artifact(task_id, agent_name, artifact_type, content)
            return {"success": True, "artifact_id": artifact.id}
        except (AuthorizationError, TaskNotFoundError) as e:
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Levanta el transporte HTTP streamable para MCP
    mcp.run(transport="sse")
