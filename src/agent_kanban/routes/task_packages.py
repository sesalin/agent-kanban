"""Transfer the input and output ZIP registered in a claimed task."""

import os
import re
import tempfile
from pathlib import Path
from zipfile import is_zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from agent_kanban.config import get_settings
from agent_kanban.models import Task, TaskStatus
from agent_kanban.permissions import require_task
from agent_kanban.routes.orchestration import DB, Agent

router = APIRouter(prefix="/api/tasks/{task_id}/package", tags=["task packages"])
MAX_ZIP_BYTES = 10 * 1024 * 1024


def package_paths(task: Task) -> tuple[Path, Path]:
    base = get_settings().muse_packages_root
    spec = task.metadata_payload.get("muse_zip")
    if not base or not isinstance(spec, dict):
        raise HTTPException(404, "Task package not available")

    folder, source, result = (spec.get(key) for key in ("path", "input_file", "output_file"))
    output_folder = spec.get("output_path", folder)
    if not all(isinstance(value, str) for value in (folder, output_folder, source, result)):
        raise HTTPException(422, "Invalid task package metadata")
    if (
        not all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", part)
            for value in (folder, output_folder) for part in value.split("/")
        )
        or not all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.zip", name) for name in (source, result)
        )
        or source.casefold() == result.casefold()
    ):
        raise HTTPException(422, "Invalid task package path or filename")

    root = Path(base).resolve()
    directories = [root / folder, root / output_folder]
    for directory in directories:
        if directory.resolve() != directory or not directory.is_dir():
            raise HTTPException(404, "Package directory not available")
    return directories[0] / source, directories[1] / result


async def claimed_task(session: DB, task_id: int, agent: Agent, *, lock: bool = False) -> Task:
    task = await require_task(session, task_id, agent, "worker", lock=lock)
    if task.claimed_by != agent or task.status != TaskStatus.IN_PROGRESS:
        raise HTTPException(403, "An in-progress claim is required")
    return task


def download(path: Path) -> FileResponse:
    if path.is_symlink() or not path.is_file():
        raise HTTPException(404, "ZIP not available")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/input")
async def get_input(task_id: int, session: DB, agent: Agent):
    source, _ = package_paths(await claimed_task(session, task_id, agent))
    return download(source)


@router.get("/result")
async def get_result(task_id: int, session: DB, agent: Agent):
    _, result = package_paths(await require_task(session, task_id, agent, "orchestrator"))
    return download(result)


@router.put("/result", status_code=201)
async def put_result(task_id: int, request: Request, session: DB, agent: Agent):
    _, result = package_paths(await claimed_task(session, task_id, agent))
    if request.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/zip":
        raise HTTPException(415, "Use application/zip with the ZIP as the request body")

    # Stage the bytes before taking a row lock so a slow upload cannot block reassignment.
    with tempfile.NamedTemporaryFile(dir=result.parent, prefix=".upload-", delete=False) as staged:
        temporary = Path(staged.name)
        try:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    raise HTTPException(413, "ZIP exceeds 10 MiB")
                await run_in_threadpool(staged.write, chunk)
            staged.close()
            if not await run_in_threadpool(is_zipfile, temporary):
                raise HTTPException(422, "The body is not a ZIP archive")
            _, current_result = package_paths(
                await claimed_task(session, task_id, agent, lock=True)
            )
            if current_result != result:
                raise HTTPException(409, "Task package changed during upload")
            try:
                await run_in_threadpool(os.link, temporary, result)
            except FileExistsError as error:
                raise HTTPException(409, "A result already exists for this package") from error
        finally:
            temporary.unlink(missing_ok=True)

    return {"filename": result.name, "bytes": size, "path": f"/api/tasks/{task_id}/package/result"}
