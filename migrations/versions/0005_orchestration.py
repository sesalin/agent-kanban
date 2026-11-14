"""Add project permissions, task orchestration and outbound webhooks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_orchestration"
down_revision = "a1b2c3d4e5f6"


def upgrade() -> None:
    op.add_column(
        "task", sa.Column("priority", sa.String(20), nullable=False, server_default="MEDIUM")
    )
    op.add_column("task", sa.Column("dependencies", JSONB, nullable=False, server_default="[]"))
    op.add_column("task", sa.Column("metadata_payload", JSONB, nullable=False, server_default="{}"))
    op.add_column(
        "task", sa.Column("created_by", sa.String(), nullable=False, server_default="system")
    )
    for name in ("last_heartbeat_at", "completed_at"):
        op.add_column("task", sa.Column(name, sa.DateTime()))
    op.add_column("task", sa.Column("git_commit_hash", sa.String()))
    op.create_index("ix_task_project_status", "task", ["project_id", "status"])
    op.create_index("ix_task_claim_lookup", "task", ["id", "status", "assigned_to"])
    op.create_index("ix_task_dependencies_gin", "task", ["dependencies"], postgresql_using="gin")

    op.create_table(
        "agent_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), nullable=False, server_default="worker"),
        sa.Column("can_read", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_claim", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
        sa.UniqueConstraint("agent_name", "project_id", name="uq_agent_project"),
        sa.CheckConstraint("role IN ('orchestrator', 'worker', 'observer')", name="ck_agent_role"),
    )
    op.create_index("ix_agent_projects_project_id", "agent_projects", ["project_id"])
    op.create_table(
        "outbound_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column("secret_token", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
    op.create_index("ix_outbound_webhooks_project_id", "outbound_webhooks", ["project_id"])
    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id", sa.Integer(), sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])


def downgrade() -> None:
    for table in ("task_events", "outbound_webhooks", "agent_projects"):
        op.drop_table(table)
    for index in ("ix_task_dependencies_gin", "ix_task_claim_lookup", "ix_task_project_status"):
        op.drop_index(index, table_name="task")
    for column in (
        "git_commit_hash",
        "completed_at",
        "last_heartbeat_at",
        "created_by",
        "metadata_payload",
        "dependencies",
        "priority",
    ):
        op.drop_column("task", column)
