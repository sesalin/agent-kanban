"""Business logic shared by REST routes and MCP tools.

Authorization rule (spec §5.3): mutations require task.claimed_by == calling agent.
We raise PermissionError on violation so callers can map to HTTP 403 / MCP error.
"""
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import case, type_coerce, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from agent_kanban import webhooks
from agent_kanban.events import event_bus
from agent_kanban.git import GitError, collect_diff, collect_diffstats, resolve_base_branch
from agent_kanban.models import (
    Artifact,
    Comment,
    ProgressEvent,
    ProgressKind,
    Project,
    Task,
    TaskEvent,
    TaskStatus,
)
from agent_kanban.permissions import (
    ProjectAccessDenied,
    authorized_projects,
    require_project,
    require_task,
)
from agent_kanban.schemas import (
    ArtifactCreate,
    ClaimResult,
    DispatchTask,
    Heartbeat,
    ProgressCreate,
    SubmitReview,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _record_event(session: AsyncSession, task: Task, event: str, agent: str, **details) -> None:
    session.add(TaskEvent(task_id=task.id, event_type=event, agent_name=agent, details=details))


async def _notify(session: AsyncSession, task: Task, event: str, agent: str) -> None:
    await webhooks.notify_task_event(
        session, task.project_id, f"TASK_{event}",
        {"task_id": task.id, "agent": agent, "status": task.status},
    )


def _to_task_read(task: Task) -> TaskRead:
    # ClaimResult.task is typed TaskRead; bridge ORM -> schema explicitly.
    return TaskRead.model_validate(task, from_attributes=True)


def _check_claimer(task: Task, agent: str) -> None:
    if task.claimed_by != agent:
        raise ProjectAccessDenied(
            f"task {task.id} is claimed by {task.claimed_by!r}, not {agent!r}"
        )


def _is_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    p = Path(path).expanduser().resolve()
    for root in allowed_roots:
        try:
            p.relative_to(Path(root).expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


async def _publish_task_event(channel: str, evt_type: str, task: Task) -> None:
    payload = {
        "type": evt_type,
        "task_id": task.id,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
    }
    await event_bus.publish(channel, payload)
    await event_bus.publish(f"task:{task.id}", payload)


# ---- Task CRUD ----
async def create_task(session: AsyncSession, data: TaskCreate) -> Task:
    task = Task(**data.model_dump())
    session.add(task)
    await session.flush()
    _record_event(session, task, "CREATED", "user")
    await session.commit()
    await _publish_task_event("board", "task_created", task)
    await _notify(session, task, "CREATED", "user")
    return task


async def update_task(session: AsyncSession, task_id: int, data: TaskUpdate) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")
    changes = data.model_dump(exclude_unset=True)
    finishing = changes.get("status") == TaskStatus.DONE and task.status != TaskStatus.DONE
    if finishing:
        await _lock_completion_project(session, task)
    for k, v in changes.items():
        setattr(task, k, v)
    task.updated_at = _now()
    unblocked = []
    if finishing:
        unblocked = await _finish_task(session, task, "user")
        _record_event(session, task, "COMPLETED", "user")
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
    if finishing:
        await _publish_unblocked(session, unblocked, "user")
        await _notify(session, task, "COMPLETED", "user")
    return task


def _assigned_to_or_open(agent: Optional[str]):
    """SQLAlchemy filter: task is unassigned OR assigned to the given agent.

    When ``agent`` is None (the REST/UI path), returns no filter — the board
    shows every task to the human operator regardless of assignment.
    """
    if agent is None:
        return None
    return (Task.assigned_to.is_(None)) | (Task.assigned_to == agent)


async def list_tasks(
    session: AsyncSession,
    status: Optional[TaskStatus] = None,
    tags_any: Optional[list[str]] = None,
    agent: Optional[str] = None,
    *,
    project_id: int | None = None,
    claimable: bool = False,
) -> list[Task]:
    """List tasks. When ``agent`` is given (MCP path), only tasks that are
    unassigned OR assigned to that agent are returned — hard-assignment hiding.
    The UI path (agent=None) sees everything."""
    stmt = select(Task).order_by(Task.sort_order, Task.created_at)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if agent is not None:
        role = "worker" if claimable else "observer"
        stmt = stmt.where(Task.project_id.in_(authorized_projects(agent, role)))
        if claimable:
            priority = case({"URGENT": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}, value=Task.priority, else_=3)
            stmt = stmt.order_by(None).order_by(priority, Task.created_at, Task.id)
    if project_id is not None:
        if agent is not None:
            await require_project(session, agent, project_id, role)
        stmt = stmt.where(Task.project_id == project_id)
    assigned_filter = _assigned_to_or_open(agent)
    if assigned_filter is not None:
        if not claimable:
            assigned_filter |= Task.project_id.in_(authorized_projects(agent, "orchestrator"))
        stmt = stmt.where(assigned_filter)
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    if tags_any:
        tasks = [t for t in tasks if any(tag in t.tags for tag in tags_any)]
    return list(tasks)


async def get_task(session: AsyncSession, task_id: int) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task {task_id} not found")
    return task


async def get_next_task(
    session: AsyncSession,
    tags_any: Optional[list[str]],
    tags_all: Optional[list[str]],
    exclude_tags: Optional[list[str]],
    agent: Optional[str] = None,
) -> Optional[Task]:
    """Return the next READY task (oldest first). When ``agent`` is given (MCP
    path), only tasks unassigned OR assigned to that agent are eligible — other
    agents' reserved tasks are invisible here."""
    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.READY)
        .order_by(Task.sort_order, Task.created_at)
    )
    assigned_filter = _assigned_to_or_open(agent)
    if assigned_filter is not None:
        stmt = stmt.where(
            assigned_filter, Task.project_id.in_(authorized_projects(agent, "worker"))
        )
    result = await session.execute(stmt)
    for task in result.scalars():
        if tags_any and not any(t in task.tags for t in tags_any):
            continue
        if tags_all and not all(t in task.tags for t in tags_all):
            continue
        if exclude_tags and any(t in task.tags for t in exclude_tags):
            continue
        return task
    return None


# ---- Claiming ----
async def claim_task(
    session: AsyncSession, task_id: int, agent: str, *, enforce_grant: bool = False
) -> ClaimResult:
    # Pre-check the hard-assignment guard so we can return a precise reason
    # ("reserved for X") instead of the generic "not ready" below.
    existing = await session.get(Task, task_id)
    if enforce_grant and existing is not None:
        await require_project(session, agent, existing.project_id, "worker")
    if existing is not None and existing.assigned_to and existing.assigned_to != agent:
        return ClaimResult(
            ok=False,
            reason=f"task is reserved for {existing.assigned_to!r}",
            task=None,
        )
    # Ownership and the grant are checked again in the atomic UPDATE.
    now = _now()
    stmt = (
        update(Task)
        .where(
            Task.id == task_id, Task.status == TaskStatus.READY,
            _assigned_to_or_open(agent),
        )
        .values(
            status=TaskStatus.IN_PROGRESS,
            claimed_by=agent,
            claimed_at=now,
            last_heartbeat_at=now,
            updated_at=now,
        )
        .returning(Task.id)
    )
    if enforce_grant:
        stmt = stmt.where(Task.project_id.in_(authorized_projects(agent, "worker")))
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        # Either doesn't exist, no longer READY, or (edge case above) reserved.
        task = await session.get(Task, task_id, populate_existing=True)
        if task is None:
            return ClaimResult(ok=False, reason="task not found")
        return ClaimResult(
            ok=False,
            reason=f"task is {task.status.value}, not ready or reserved",
            task=None,
        )
    task = await session.get(Task, task_id, populate_existing=True)
    assert task is not None
    _record_event(session, task, "CLAIMED", agent)
    await session.commit()
    await _publish_task_event("board", "task_claimed", task)
    await _notify(session, task, "CLAIMED", agent)
    return ClaimResult(ok=True, task=_to_task_read(task))


# ---- Progress ----
async def post_progress(
    session: AsyncSession, task_id: int, data: ProgressCreate, *, enforce_grant: bool = False
) -> ProgressEvent:
    if enforce_grant:
        task = await _owned_task(session, task_id, data.agent)
    else:
        task = await get_task(session, task_id)
        _check_claimer(task, data.agent)
    task.last_heartbeat_at = _now()
    payload: dict = {"content": data.content}
    if data.kind.value == "artifact_ref" and data.artifact:
        # Copy so we can mutate; data.artifact is the agent-supplied dict.
        payload["artifact"] = dict(data.artifact)
        # Look up the most recent Artifact row for this task + path so the UI
        # can fetch the file via /api/artifacts/{id}/content. Never raises — a
        # select won't fail; if no row matches, the payload is left as-is and
        # the UI falls back to the file:/// path.
        art_path = data.artifact.get("path")
        if art_path:
            stmt = (
                select(Artifact)
                .where(Artifact.task_id == task_id, Artifact.path == art_path)
                .order_by(Artifact.id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalars().first()
            if row is not None:
                payload["artifact"]["id"] = row.id
    blocked = False
    if data.kind.value == "status_change" and data.status:
        payload["status"] = data.status
        if data.status.get("to") == "blocked":
            task.status = TaskStatus.BLOCKED
            task.updated_at = datetime.now(UTC).replace(tzinfo=None)
            blocked = True
    ev = ProgressEvent(
        task_id=task_id,
        agent=data.agent,
        kind=data.kind,
        payload=payload,
    )
    session.add(ev)
    _record_event(session, task, "PROGRESS", data.agent)
    await session.commit()
    await session.refresh(ev)
    await _notify(session, task, "PROGRESS", data.agent)
    if blocked:
        # Lifecycle event fans out to the board channel AND task:{id}. Skip the
        # redundant task-channel "progress" publish below so subscribers see a
        # single authoritative "task_blocked" event for this transition.
        await session.refresh(task)
        await _publish_task_event("board", "task_blocked", task)
        return ev
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "progress", "event_id": ev.id, "kind": ev.kind.value},
    )
    return ev


async def complete_task(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str] = None,
    *, enforce_grant: bool = False,
) -> Task:
    task = (
        await require_task(session, task_id, agent, "worker")
        if enforce_grant else await get_task(session, task_id)
    )
    original_project = task.project_id
    await _lock_completion_project(session, task)
    if enforce_grant:
        task = await _owned_task(session, task_id, agent)
        if task.project_id != original_project or await _was_dispatched(session, task):
            raise ProjectAccessDenied("dispatched tasks must be submitted for orchestrator review")
    else:
        _check_claimer(task, agent)
    if summary:
        session.add(
            ProgressEvent(
                task_id=task_id,
                agent=agent,
                kind=ProgressKind.TEXT,
                payload={"content": summary},
            )
        )
    unblocked = await _finish_task(session, task, agent)
    _record_event(session, task, "COMPLETED", agent)
    await session.commit()
    await _publish_task_event("board", "task_completed", task)
    await _publish_unblocked(session, unblocked, agent)
    await _notify(session, task, "COMPLETED", agent)
    return task


async def _maybe_collect_review_diff(
    session: AsyncSession, task: Task, agent: str
) -> None:
    """Best-effort: if the task has repo_path + branch + a resolvable base,
    collect the diff and store it as a progress_event(kind=diff). On git
    failure, store a kind=error event so the user sees what went wrong.
    Never raises — review must succeed regardless of git.
    """
    if not task.repo_path or not task.branch:
        return
    base = await resolve_base_branch(session, task)
    if base is None:
        return
    # Collect the unified diff — failure here means we can't render anything.
    try:
        diff_text = await collect_diff(task.repo_path, base, task.branch)
    except GitError as exc:
        session.add(
            ProgressEvent(
                task_id=task.id,
                agent=agent,
                kind="error",
                payload={"content": f"diff collection failed: {exc}"},
            )
        )
        return
    except Exception as exc:  # defensive: never break review on a git surprise
        session.add(
            ProgressEvent(
                task_id=task.id,
                agent=agent,
                kind="error",
                payload={"content": f"diff collection raised {type(exc).__name__}: {exc}"},
            )
        )
        return

    # Collect per-file stats — failure here degrades to empty stats, not a lost diff.
    try:
        diffstats = await collect_diffstats(task.repo_path, base, task.branch)
    except Exception:
        diffstats = []

    files = [s["path"] for s in diffstats]
    stats = {
        s["path"]: (
            f"+{s['added']} -{s['deleted']}" if s["added"] >= 0 and s["deleted"] >= 0
            else "binary"
        )
        for s in diffstats
    }
    session.add(
        ProgressEvent(
            task_id=task.id,
            agent=agent,
            kind="diff",
            payload={"content": diff_text, "files": files, "stats": stats},
        )
    )


async def request_review(
    session: AsyncSession, task_id: int, agent: str, summary: Optional[str] = None,
    *, enforce_grant: bool = False,
) -> Task:
    if enforce_grant:
        task = await _owned_task(session, task_id, agent)
        if await _was_dispatched(session, task):
            return await submit_for_review(
                session, task_id, agent, SubmitReview(summary_of_work=summary or "")
            )
    else:
        task = await get_task(session, task_id)
        _check_claimer(task, agent)
    task.status = TaskStatus.REVIEW
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    if summary:
        session.add(
            ProgressEvent(
                task_id=task_id,
                agent=agent,
                kind="text",
                payload={"content": summary},
            )
        )
    # Phase 3: best-effort diff auto-collection.
    await _maybe_collect_review_diff(session, task, agent)
    _record_event(session, task, "SUBMITTED", agent, summary=summary)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_review_requested", task)
    await _notify(session, task, "SUBMITTED", agent)
    return task


async def set_task_branch(
    session: AsyncSession, task_id: int, agent: str, branch: str, *, enforce_grant: bool = False
) -> Task:
    if enforce_grant:
        task = await _owned_task(session, task_id, agent)
    else:
        task = await get_task(session, task_id)
        _check_claimer(task, agent)
    task.branch = branch
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
    return task


async def set_task_pr(
    session: AsyncSession,
    task_id: int,
    agent: str,
    pr_url: str,
    pr_status: str,
    *, enforce_grant: bool = False,
) -> Task:
    if enforce_grant:
        task = await _owned_task(session, task_id, agent)
    else:
        task = await get_task(session, task_id)
        _check_claimer(task, agent)
    task.pr_url = pr_url
    task.pr_status = pr_status
    task.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(task)
    await _publish_task_event("board", "task_updated", task)
    return task


# ---- Comments ----
async def list_comments(
    session: AsyncSession,
    task_id: int,
    since_id: Optional[int],
    mark_seen_by: Optional[str],
) -> list[Comment]:
    stmt = select(Comment).where(Comment.task_id == task_id)
    if since_id is not None:
        stmt = stmt.where(Comment.id > since_id)
    # Unseen first.
    stmt = stmt.order_by(Comment.seen_by_agent.asc(), Comment.id.asc())
    result = await session.execute(stmt)
    comments = list(result.scalars())
    if mark_seen_by is not None:
        # seen_by_agent is a read-receipt for messages TO the agent. The reading
        # agent should not mark its own comments as "seen by itself" — they were
        # authored by it, never "unseen" from its perspective.
        for c in comments:
            if not c.seen_by_agent and c.author != mark_seen_by:
                c.seen_by_agent = True
        await session.commit()
    return comments


async def post_comment(
    session: AsyncSession, task_id: int, author: str, content: str
) -> Comment:
    c = Comment(task_id=task_id, author=author, content=content)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "comment", "comment_id": c.id, "author": author},
    )
    return c


async def post_comment_with_status(
    session: AsyncSession,
    task_id: int,
    author: str,
    content: str,
    target_status: Optional[TaskStatus],
) -> Comment:
    """Post a comment and optionally transition the task status, atomically.

    Both the comment insert and the status update commit together. If the
    status update fails, the comment is not persisted either.
    """
    # Validate task exists.
    task = await get_task(session, task_id)
    # Insert comment (no commit yet).
    c = Comment(task_id=task_id, author=author, content=content)
    session.add(c)
    unblocked = []
    finishing = target_status == TaskStatus.DONE and task.status != TaskStatus.DONE
    if finishing:
        await _lock_completion_project(session, task)
        unblocked = await _finish_task(session, task, author)
        _record_event(session, task, "COMPLETED", author)
    elif target_status is not None:
        task.status = target_status
        task.updated_at = _now()
    # Single commit for both.
    await session.commit()
    await session.refresh(c)
    await event_bus.publish(
        f"task:{task_id}",
        {"type": "comment", "comment_id": c.id, "author": author},
    )
    if target_status is not None:
        await _publish_task_event("board", "task_updated", task)
    if finishing:
        await _publish_unblocked(session, unblocked, author)
        await _notify(session, task, "COMPLETED", author)
    return c


# ---- Artifacts ----
async def post_artifact(
    session: AsyncSession, task_id: int, data: ArtifactCreate, *, enforce_grant: bool = False
) -> Artifact:
    if enforce_grant:
        task = await _owned_task(session, task_id, data.agent)
    else:
        task = await get_task(session, task_id)
        _check_claimer(task, data.agent)
    allowed_roots = [
        Path.home() / ".agent-kanban" / "artifacts" / str(task_id),
    ]
    if task.repo_path:
        allowed_roots.append(task.repo_path)
    if not _is_path_allowed(data.path, [str(r) for r in allowed_roots]):
        raise ValueError(
            f"artifact path {data.path!r} is not inside an allowed root"
        )
    # NOTE: ArtifactCreate carries `agent` for authorization, but the Artifact
    # table has no agent column — drop it before constructing the ORM object.
    art = Artifact(task_id=task_id, **data.model_dump(exclude={"agent"}))
    session.add(art)
    await session.commit()
    await session.refresh(art)
    return art


# ---- Agent orchestration ----
async def dispatch_task(session: AsyncSession, agent: str, data: DispatchTask) -> Task:
    await require_project(session, agent, data.project_id, "orchestrator")
    # Serialize dispatch and completion so a dependency cannot finish during dispatch.
    await session.get(Project, data.project_id, with_for_update=True)
    if data.assigned_to is not None:
        await require_project(session, data.assigned_to, data.project_id, "worker")
    dependencies = list(dict.fromkeys(data.dependencies))
    states = dict((await session.execute(
        select(Task.id, Task.status).where(
            Task.project_id == data.project_id, Task.id.in_(dependencies)
        )
    )).all())
    if len(states) != len(dependencies):
        raise ValueError("dependencies must exist in the same project")
    task = Task(
        **data.model_dump(exclude={"metadata", "dependencies"}),
        dependencies=dependencies,
        metadata_payload=data.metadata,
        created_by=agent,
        status=TaskStatus.BLOCKED if dependencies else TaskStatus.READY,
    )
    # Approval may already have happened before dispatch.
    if dependencies and all(status == TaskStatus.DONE for status in states.values()):
        task.status = TaskStatus.READY
    session.add(task)
    await session.flush()
    _record_event(session, task, "CREATED", agent, dispatched=True)
    await session.commit()
    await _publish_task_event("board", "task_created", task)
    await _notify(session, task, "CREATED", agent)
    return task


async def _was_dispatched(session: AsyncSession, task: Task) -> bool:
    query = select(TaskEvent.id).where(
        TaskEvent.task_id == task.id,
        TaskEvent.event_type == "CREATED",
        TaskEvent.details["dispatched"].as_boolean().is_(True),
    )
    return (await session.execute(query.limit(1))).scalar_one_or_none() is not None


async def _finish_task(session: AsyncSession, task: Task, agent: str) -> list[Task]:
    task.status = TaskStatus.DONE
    task.updated_at = task.completed_at = _now()
    await session.flush()
    if task.project_id is None:
        return []

    query = select(Task).where(Task.project_id == task.project_id, Task.status == TaskStatus.BLOCKED)
    query = query.where(type_coerce(Task.dependencies, JSONB).contains([task.id]))
    candidates = (await session.execute(query.order_by(Task.id).with_for_update())).scalars()
    unblocked = []
    for dependent in candidates:
        done = (await session.execute(select(Task.id).where(
            Task.project_id == task.project_id,
            Task.id.in_(dependent.dependencies),
            Task.status == TaskStatus.DONE,
        ))).scalars()
        if set(done) == set(dependent.dependencies):
            dependent.status = TaskStatus.READY
            dependent.updated_at = task.completed_at
            _record_event(session, dependent, "UNBLOCKED", agent, dependency_id=task.id)
            unblocked.append(dependent)
    return unblocked


async def _publish_unblocked(
    session: AsyncSession, tasks: list[Task], agent: str
) -> None:
    for task in tasks:
        await _publish_task_event("board", "task_updated", task)
        await _notify(session, task, "UNBLOCKED", agent)


async def _lock_completion_project(session: AsyncSession, task: Task) -> None:
    if task.project_id is not None:
        await session.get(Project, task.project_id, with_for_update=True)


async def review_task(
    session: AsyncSession, task_id: int, agent: str, verdict: str, feedback: str = ""
) -> Task:
    task = await require_task(session, task_id, agent, "orchestrator")
    original_project = task.project_id
    await _lock_completion_project(session, task)
    task = await require_task(session, task_id, agent, "orchestrator", lock=True)
    if task.project_id != original_project or task.status != TaskStatus.REVIEW:
        raise ValueError("task must be in review")
    unblocked = []
    if verdict == "APPROVE":
        unblocked = await _finish_task(session, task, agent)
        event = "APPROVED"
    elif verdict == "REJECT":
        task.status = TaskStatus.IN_PROGRESS if task.claimed_by else TaskStatus.READY
        task.updated_at = _now()
        if task.claimed_by:
            task.last_heartbeat_at = task.updated_at
        event = "REJECTED"
    else:
        raise ValueError("verdict must be APPROVE or REJECT")
    if feedback:
        session.add(Comment(task_id=task_id, author=agent, content=feedback))
    _record_event(session, task, event, agent, feedback=feedback)
    await session.commit()
    await _publish_task_event("board", "task_updated", task)
    await _publish_unblocked(session, unblocked, agent)
    await _notify(session, task, event, agent)
    return task


async def reassign_stalled_task(
    session: AsyncSession, task_id: int, agent: str, new_agent_name: str
) -> Task:
    task = await require_task(session, task_id, agent, "orchestrator", lock=True)
    await require_project(session, new_agent_name, task.project_id, "worker")
    now = _now()
    last_active = task.last_heartbeat_at or task.claimed_at or task.updated_at
    if task.status != TaskStatus.IN_PROGRESS or now - last_active < timedelta(minutes=15):
        raise ValueError("task must be in progress without activity for at least 15 minutes")
    previous_agent = task.claimed_by
    task.status = TaskStatus.READY
    task.assigned_to = new_agent_name
    task.claimed_by = task.claimed_at = task.last_heartbeat_at = None
    task.updated_at = now
    _record_event(session, task, "REASSIGNED", agent, previous_agent=previous_agent, assigned_to=new_agent_name)
    await session.commit()
    await _publish_task_event("board", "task_updated", task)
    await _notify(session, task, "REASSIGNED", agent)
    return task


async def _owned_task(session: AsyncSession, task_id: int, agent: str) -> Task:
    task = await require_task(session, task_id, agent, "worker", lock=True)
    _check_claimer(task, agent)
    if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED):
        raise ValueError("task must be in progress or blocked by its worker")
    return task


async def heartbeat_and_progress(
    session: AsyncSession, task_id: int, agent: str, data: Heartbeat
) -> Task:
    task = await _owned_task(session, task_id, agent)
    task.updated_at = task.last_heartbeat_at = _now()
    for key, value in (
        ("branch", data.git_branch), ("pr_url", data.git_pr_url), ("git_commit_hash", data.git_commit_hash)
    ):
        if value is not None:
            setattr(task, key, value)
    if data.notes:
        session.add(ProgressEvent(
            task_id=task_id, agent=agent, kind=ProgressKind.TEXT, payload={"content": data.notes}
        ))
    _record_event(session, task, "PROGRESS", agent, notes=data.notes)
    await session.commit()
    await _publish_task_event("board", "task_updated", task)
    await _notify(session, task, "PROGRESS", agent)
    return task


async def submit_for_review(
    session: AsyncSession, task_id: int, agent: str, data: SubmitReview
) -> Task:
    task = await _owned_task(session, task_id, agent)
    task.status = TaskStatus.REVIEW
    task.updated_at = task.last_heartbeat_at = _now()
    session.add(ProgressEvent(
        task_id=task_id, agent=agent, kind=ProgressKind.TEXT,
        payload={"content": data.summary_of_work},
    ))
    for artifact in data.artifacts:
        session.add(ProgressEvent(
            task_id=task_id, agent=agent, kind=ProgressKind.TEXT, payload={"content": artifact}
        ))
    _record_event(session, task, "SUBMITTED", agent, summary=data.summary_of_work, artifacts=data.artifacts)
    await session.commit()
    await _publish_task_event("board", "task_review_requested", task)
    await _notify(session, task, "SUBMITTED", agent)
    return task
