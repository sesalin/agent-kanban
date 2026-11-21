"""Daily factory windows and the shared Muse claim guard."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlmodel import select

from agent_kanban.models import Task, TaskStatus

ZONE = ZoneInfo("America/Mexico_City")
# Windows allow finishing an existing claim after the end; only new claims are gated.
SLOTS = {
    "research": (635, 750),
    "evaluation": (780, 870),
    "mvp": (900, 1050),
    "prospection": (900, 1050),
    "landing": (900, 1050),
    "final": (1110, 1170),
}
ACTORS = {
    "research": "brio",
    "evaluation": "bacha",
    "mvp": "codex",
    "prospection": "bacha",
    "landing": "dot",
    "final": "bacha",
}


def local_now():
    return datetime.now(UTC).astimezone(ZONE)


def slot_open(step, now=None):
    now = (now or local_now()).astimezone(ZONE)
    minute = now.hour * 60 + now.minute
    start, end = SLOTS[step]
    return start <= minute < end


async def claim_blocker(session, task, agent):
    sequential = task.metadata_payload.get("factory_mode") == "sequential"
    if sequential:
        step = task.metadata_payload.get("factory_step")
        if step not in SLOTS or ACTORS[step] != agent:
            return "invalid factory step or identity"
        if not slot_open(step):
            return "outside the daily factory window (America/Mexico_City)"
    # Serialize claims for the same identity across every project and app process.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:agent, 7331003))"),
        {"agent": agent},
    )
    active = (await session.execute(select(Task).where(
        Task.claimed_by == agent, Task.status == TaskStatus.IN_PROGRESS,
        Task.id != task.id,
    ))).scalars().first()
    if active:
        return f"WIP=1: {agent} busy on task {active.id}"
    if agent in ("brio", "bacha"):
        # Serialize all Muse claims, including legacy cards, until the claiming transaction commits.
        await session.execute(text("SELECT pg_advisory_xact_lock(7331002)"))
        active = (
            (
                await session.execute(
                    select(Task).where(
                        Task.project_id == 1,
                        Task.status == TaskStatus.IN_PROGRESS,
                        Task.claimed_by.in_(("brio", "bacha")),
                        Task.id != task.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for other in active:
            if sequential or other.metadata_payload.get("factory_mode") == "sequential":
                return (
                    f"Muse busy on task {other.id}; finish or explicitly recover that claim first"
                )
    return None
