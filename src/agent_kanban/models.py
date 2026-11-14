"""SQLModel ORM models matching spec §4.1."""
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON, Column, Field, SQLModel


class TaskStatus(str, Enum):
    TODO = "todo"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class ProgressKind(str, Enum):
    TEXT = "text"
    DIFF = "diff"
    ARTIFACT_REF = "artifact_ref"
    ERROR = "error"
    STATUS_CHANGE = "status_change"


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    repo_path: Optional[str] = None
    default_branch: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Task(SQLModel, table=True):
    __table_args__ = (
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_claim_lookup", "id", "status", "assigned_to"),
        Index("ix_task_dependencies_gin", "dependencies", postgresql_using="gin"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, foreign_key="project.id")
    title: str
    description: str = ""
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        sa_column=Column(
            SAEnum(
                TaskStatus,
                name="taskstatus",
                values_callable=lambda e: [m.value for m in e],
            ),
            index=True,
        ),
    )
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    claimed_by: Optional[str] = Field(default=None, index=True)
    claimed_at: Optional[datetime] = None
    # Hard assignment: an operator reserves a task for a specific agent. The
    # task is then visible (in get_next_task / list_tasks) and claimable only by
    # that agent. Other agents don't see it. Set/cleared via REST PATCH by a
    # human operator — agents themselves cannot assign.
    assigned_to: Optional[str] = Field(default=None, index=True)
    sort_order: float = Field(default=0.0)
    priority: str = Field(default="MEDIUM", max_length=20)
    dependencies: list[int] = Field(
        default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    )
    metadata_payload: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    )
    created_by: str = Field(default="system")
    last_heartbeat_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    git_commit_hash: Optional[str] = None
    # Phase 3 fields (present now so migrations are stable; unused in Phase 1)
    repo_path: Optional[str] = None
    base_branch: Optional[str] = None
    branch: Optional[str] = None
    pr_url: Optional[str] = None
    pr_status: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class ProgressEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    agent: str
    kind: ProgressKind = Field(
        sa_column=Column(
            SAEnum(
                ProgressKind,
                name="progresskind",
                values_callable=lambda e: [m.value for m in e],
            )
        )
    )
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)


class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    author: str
    content: str
    seen_by_agent: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)


class Artifact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    path: str
    kind: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    is_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Token(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str = Field(index=True)
    token_hash: str  # bcrypt hash of the opaque token
    token_prefix: str = Field(default="", index=True)  # first 8 chars of plaintext, for fast lookup
    description: Optional[str] = None
    created_by_user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    last_used_at: Optional[datetime] = None


class AgentProject(SQLModel, table=True):
    __tablename__ = "agent_projects"
    __table_args__ = (
        UniqueConstraint("agent_name", "project_id", name="uq_agent_project"),
        CheckConstraint("role IN ('orchestrator', 'worker', 'observer')", name="ck_agent_role"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_name: str
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    role: str = Field(default="worker", max_length=30)
    can_read: bool = True
    can_claim: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class OutboundWebhook(SQLModel, table=True):
    __tablename__ = "outbound_webhooks"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True, ondelete="CASCADE")
    target_url: str
    secret_token: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class TaskEvent(SQLModel, table=True):
    __tablename__ = "task_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True, ondelete="CASCADE")
    event_type: str = Field(max_length=50)
    agent_name: str
    details: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
