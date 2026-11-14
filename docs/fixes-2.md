
---

# PROMPT / ESPECIFICACIÓN TÉCNICA PARA CODEX

> **Rol del agente:** Eres un ingeniero backend senior especializado en Python, FastAPI, SQLModel/SQLAlchemy y PostgreSQL 17.
> **Objetivo:** Extender y blindar `agent-kanban` para soportar aislamiento multi-proyecto, orquestación autónoma mediante roles (`orchestrator` vs `worker`), resolución automática de dependencias y webhooks de eventos para sincronización externa.

---

## 1. Migración SQL DDL (`migrations/002_orchestration_and_security.sql`)

Aplica estos cambios sobre la base de datos PostgreSQL 17:

```sql
-- 1. Tabla de roles y permisos por agente y proyecto
CREATE TABLE IF NOT EXISTS agent_projects (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    project_id VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'worker', -- 'orchestrator' | 'worker' | 'observer'
    can_claim BOOLEAN NOT NULL DEFAULT TRUE,
    can_read BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_project UNIQUE (agent_name, project_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_projects_lookup
ON agent_projects (agent_name, project_id);

-- 2. Alteración a la tabla tasks existente
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS project_id VARCHAR(100) NOT NULL DEFAULT 'default',
    ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    ADD COLUMN IF NOT EXISTS dependencies JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS last_heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(100) NOT NULL DEFAULT 'system';

-- Índices de consulta de tareas
CREATE INDEX IF NOT EXISTS idx_tasks_project_status
ON tasks (project_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_dependencies_gin
ON tasks USING gin (dependencies);

-- 3. Tabla de Webhooks para despacho de eventos externos (ej. n8n / Orquestador)
CREATE TABLE IF NOT EXISTS outbound_webhooks (
    id SERIAL PRIMARY KEY,
    project_id VARCHAR(100) NOT NULL,
    target_url TEXT NOT NULL,
    secret_token VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_project
ON outbound_webhooks (project_id) WHERE is_active = TRUE;

-- 4. Registro de auditoría y eventos de tareas
CREATE TABLE IF NOT EXISTS task_events (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- 'CREATED', 'CLAIMED', 'PROGRESS', 'SUBMITTED', 'APPROVED', 'REJECTED', 'UNBLOCKED'
    agent_name VARCHAR(100) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_id
ON task_events (task_id);

```

---

## 2. Modelos SQLModel (`models.py`)

Asegúrate de actualizar o extender las definiciones de clases:

```python
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

class AgentProject(SQLModel, table=True):
    __tablename__ = "agent_projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True)
    project_id: str = Field(index=True)
    role: str = Field(default="worker") # 'orchestrator' | 'worker'
    can_claim: bool = Field(default=True)
    can_read: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OutboundWebhook(SQLModel, table=True):
    __tablename__ = "outbound_webhooks"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True)
    target_url: str
    secret_token: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: str = Field(primary_key=True)
    project_id: str = Field(default="default", index=True)
    title: str
    description: str
    status: str = Field(default="READY")  # READY, IN_PROGRESS, IN_REVIEW, DONE, BLOCKED, CANCELLED
    priority: str = Field(default="MEDIUM")
    assigned_to: Optional[str] = Field(default=None, index=True)
    created_by: str = Field(default="orchestrator")

    # Soporte JSONB nativo para Postgres
    dependencies: List[str] = Field(default=[], sa_column=Column(JSONB))
    metadata_payload: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

    created_at: datetime = Field(default_factory=datetime.utcnow)
    claimed_at: Optional[datetime] = None
    last_heartbeat_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

```

---

## 3. Disparador de Webhooks Asíncrono (`webhooks.py`)

Crea un módulo ligero para despachar eventos sin trabar la transacción de Postgres:

```python
import httpx
import asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from models import OutboundWebhook

async def notify_task_event(session: AsyncSession, project_id: str, event_type: str, payload: dict):
    """Obtiene webhooks activos del proyecto y envía el evento en segundo plano."""
    stmt = select(OutboundWebhook).where(
        OutboundWebhook.project_id == project_id,
        OutboundWebhook.is_active == True
    )
    res = await session.execute(stmt)
    webhooks = res.scalars().all()
    if not webhooks:
        return

    async def _send(url: str, token: str | None, body: dict):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Webhook-Secret"] = token
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=body, headers=headers)
        except Exception:
            pass # Fail-silent para no romper la ejecución local

    body = {
        "event": event_type,
        "project_id": project_id,
        "data": payload
    }

    for wh in webhooks:
        asyncio.create_task(_send(wh.target_url, wh.secret_token, body))

```

---

## 4. Lógica de Servicios y Desbloqueo Autónomo (`services.py`)

Implementa la resolución de dependencias cuando una tarea pasa a `DONE`:

```python
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime
from models import Task, AgentProject
from webhooks import notify_task_event

async def verify_permissions(session: AsyncSession, agent_name: str, project_id: str, required_role: str = "worker") -> bool:
    stmt = select(AgentProject).where(
        AgentProject.agent_name == agent_name,
        AgentProject.project_id == project_id
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if not record or not record.can_read:
        return False
    if required_role == "orchestrator" and record.role != "orchestrator":
        return False
    return True

async def atomic_claim_task(session: AsyncSession, task_id: str, agent_name: str) -> Task:
    # 1. Obtener proyecto y validar permisos
    stmt_task = select(Task).where(Task.id == task_id)
    task = (await session.execute(stmt_task)).scalar_one_or_none()
    if not task:
        raise ValueError("Tarea no encontrada")

    if not await verify_permissions(session, agent_name, task.project_id, "worker"):
        raise PermissionError(f"Agente {agent_name} no autorizado en {task.project_id}")

    # 2. UPDATE Atómico estricto
    stmt = (
        update(Task)
        .where(
            Task.id == task_id,
            Task.status == "READY",
            (Task.assigned_to.is_(None) | (Task.assigned_to == agent_name))
        )
        .values(
            status="IN_PROGRESS",
            assigned_to=agent_name,
            claimed_at=datetime.utcnow(),
            last_heartbeat_at=datetime.utcnow()
        )
        .execution_options(synchronize_session="fetch")
    )
    res = await session.execute(stmt)
    if res.rowcount == 0:
        raise ValueError("No se pudo reclamar la tarea (estado no READY o asignada a otro agente)")

    await session.commit()
    await notify_task_event(session, task.project_id, "TASK_CLAIMED", {"task_id": task_id, "agent": agent_name})
    return task

async def approve_and_unblock_dependents(session: AsyncSession, task_id: str, reviewer_agent: str):
    """Marca la tarea como DONE y desbloquea tareas que dependían de ella."""
    stmt_task = select(Task).where(Task.id == task_id)
    task = (await session.execute(stmt_task)).scalar_one_or_none()
    if not task:
        raise ValueError("Tarea no encontrada")

    task.status = "DONE"
    task.completed_at = datetime.utcnow()
    session.add(task)
    await session.flush()

    # Buscar tareas BLOCKED del mismo proyecto
    stmt_blocked = select(Task).where(
        Task.project_id == task.project_id,
        Task.status == "BLOCKED"
    )
    blocked_tasks = (await session.execute(stmt_blocked)).scalars().all()

    # Verificar qué tareas hijas ya tienen todas sus dependencias en DONE
    for b_task in blocked_tasks:
        if task_id in b_task.dependencies:
            # Consultar estado de todas las dependencias de esta tarea
            stmt_deps = select(Task.status).where(Task.id.in_(b_task.dependencies))
            statuses = (await session.execute(stmt_deps)).scalars().all()

            if all(s == "DONE" for s in statuses):
                b_task.status = "READY"
                session.add(b_task)
                await notify_task_event(session, task.project_id, "TASK_UNBLOCKED", {"task_id": b_task.id})

    await session.commit()
    await notify_task_event(session, task.project_id, "TASK_APPROVED", {"task_id": task_id, "by": reviewer_agent})

```

---

## 5. Herramientas MCP Expuestas (`mcp_server.py`)

Organiza las tools dividiendo las del Orquestador de las del Worker:

### Para el Orquestador:

* `dispatch_task`:
* Args: `project_id`, `title`, `description`, `assigned_to` (opcional), `priority`, `dependencies` (list[str]), `metadata` (dict).
* Regla: Valida que el agente sea `orchestrator`. Si tiene `dependencies`, arranca en `BLOCKED`; si no, en `READY`.


* `review_task`:
* Args: `task_id`, `verdict` (`APPROVE` | `REJECT`), `feedback`.
* Regla: Si `APPROVE`, llama a `approve_and_unblock_dependents`. Si `REJECT`, regresa a `IN_PROGRESS` o `READY` y añade el feedback en comentarios.


* `reassign_stalled_task`:
* Args: `task_id`, `new_agent_name`.
* Regla: Resetea el ownership si un worker se cayó o no renovó `last_heartbeat_at`.



### Para el Worker (Codex, Qoder, etc.):

* `list_my_tasks`:
* Args: `project_id`.
* Retorna: Tareas en `READY` donde `assigned_to == caller` o `assigned_to IS NULL`, pertenecientes a los proyectos autorizados.


* `claim_task`:
* Args: `task_id`.
* Ejecuta la reserva atómica.


* `heartbeat_and_progress`:
* Args: `task_id`, `notes`.
* Actualiza `last_heartbeat_at` para no ser considerado huérfano.


* `submit_for_review`:
* Args: `task_id`, `summary_of_work`, `artifacts` (lista de rutas, PR URLs o diffs).
* Mueve la tarea a `IN_REVIEW` y detona el webhook para que el orquestador sepa que debe revisar.



---

### Verificación para Codex

Indícale a Codex que al terminar ejecute:

1. Las migraciones con `alembic` o el script SQL directo en PostgreSQL.
2. Un test de aislamiento: crear una tarea en `project_id = "A"` e intentar llamarla con un token asignado únicamente a `project_id = "B"` (debe retornar `403 / PermissionError`).
3. Un test de dependencias: crear Tarea 2 dependiente de Tarea 1. Verificar que Tarea 2 nace en `BLOCKED`, y pasa automáticamente a `READY` cuando Tarea 1 es aprobada.
