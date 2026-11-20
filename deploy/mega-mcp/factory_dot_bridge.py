"""Task-scoped Dot access to Agent Kanban; credentials never cross the MCP boundary."""

import hashlib
import json
import os
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from app.mcp.audit import register_traced_tool
from mcp.server.fastmcp import FastMCP

MAX_ZIP = 10 * 1024 * 1024
MAX_INPUT = 32 * 1024 * 1024
MAX_TEXT = 256 * 1024


def _base_url() -> str:
    url = os.getenv("FACTORY_DOT_KANBAN_URL", "http://host.docker.internal:7331").rstrip("/")
    if url not in ("http://host.docker.internal:7331", "https://kanban-api.okehc.com"):
        raise ValueError("Dot bridge target is not allowed")
    return url


def _request(
    method: str,
    path: str,
    payload: dict | None = None,
    binary: bytes | None = None,
    zip_response: bool = False,
) -> Any:
    token = os.getenv("FACTORY_DOT_KANBAN_TOKEN", "").strip()
    if not token:
        raise ValueError("Dot bridge credential is not configured")
    body = (
        binary
        if binary is not None
        else json.dumps(payload).encode()
        if payload is not None
        else None
    )
    req = Request(
        _base_url() + path,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/zip" if zip_response else "application/json",
            "Content-Type": "application/zip" if binary is not None else "application/json",
            "User-Agent": "MegaMCP-Dot/1.0",
        },
    )
    # Never follow redirects with the server-held token.
    from urllib.request import HTTPRedirectHandler, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        with build_opener(NoRedirect).open(req, timeout=20) as response:
            media = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if media != ("application/zip" if zip_response else "application/json"):
                raise ValueError("Kanban returned an unexpected content type")
            maximum = MAX_INPUT if zip_response else 2 * 1024 * 1024
            data = response.read(maximum + 1)
            if len(data) > maximum:
                raise ValueError("Kanban response exceeds bridge limit")
    except HTTPError as error:
        detail = ""
        try:
            value = json.loads(error.read(4096)).get("detail", "")
            if isinstance(value, str):
                detail = value.replace(token, "[REDACTED]")[:240]
        except (ValueError, AttributeError):
            pass
        raise ValueError(f"Kanban HTTP {error.code}: {detail}") from None
    except (URLError, TimeoutError):
        raise ValueError("Kanban is unavailable") from None
    return data if zip_response else json.loads(data)


def _id(task_id: int) -> int:
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise ValueError("task_id must be a positive integer")
    return task_id


def _task(task_id: int, claimed: bool = False) -> dict:
    task = _request("GET", f"/api/tasks/{_id(task_id)}")
    if task.get("project_id") != 1 or task.get("assigned_to") != "dot":
        raise ValueError("Only tasks assigned to dot in project 1 are allowed")
    if claimed and (task.get("status") != "in_progress" or task.get("claimed_by") != "dot"):
        raise ValueError("An active Dot claim is required")
    return task


def _relative(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 240 or "\\" in path:
        raise ValueError("Invalid relative filename")
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ("", ".", "..") for part in path.split("/")) or ":" in path:
        raise ValueError("Filename must stay inside this task")
    return path


def _safe(root: Path, relative: str) -> Path:
    target = root / _relative(relative)
    if target.absolute() != target.resolve() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Symlinks and paths outside the task are not allowed")
    return target


def _work(task: dict) -> Path:
    import re

    meta = task.get("metadata_payload", {})
    event = meta.get("event_id", "")
    spec = meta.get("muse_zip", {})
    if not isinstance(event, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", event):
        raise ValueError("Invalid task event")
    expected = {
        "path": event + "/03_specs",
        "input_file": "landing-input.zip",
        "output_path": event + "/06_landing",
        "output_file": "landing.zip",
    }
    if meta.get("factory_step") != "landing" or any(spec.get(k) != v for k, v in expected.items()):
        raise ValueError("Task is not a canonical landing package")
    root = Path(os.getenv("FACTORY_DOT_PACKAGES_ROOT", "/muse-packages"))
    if root.absolute() != root.resolve() or not root.is_dir():
        raise ValueError("Package root is not available")
    work = _safe(root, event + "/06_landing/.dot-work/task-" + str(task["id"]))
    work.mkdir(parents=True, exist_ok=True)
    return work


def _archive(task_id: int, archive: str = "") -> ZipFile:
    _work(_task(task_id, claimed=True))
    raw = _request("GET", f"/api/tasks/{task_id}/package/input", zip_response=True)
    try:
        result = ZipFile(BytesIO(raw))
        if archive:
            info = result.getinfo(_relative(archive))
            if info.file_size > MAX_INPUT:
                raise ValueError("Nested ZIP is too large")
            raw = result.read(info)
            result.close()
            result = ZipFile(BytesIO(raw))
        infos = result.infolist()
        if len(infos) > 512 or sum(i.file_size for i in infos) > 100 * 1024 * 1024:
            result.close()
            raise ValueError("Input archive exceeds limits")
        return result
    except (BadZipFile, KeyError):
        raise ValueError("Input is not a readable ZIP or member was not found") from None


def _text(data: bytes, start_line: int, max_lines: int) -> dict:
    if not 1 <= start_line or not 1 <= max_lines <= 300:
        raise ValueError("Invalid line range; max_lines is at most 300")
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise ValueError("This tool reads UTF-8 text only") from None
    content = "\n".join(lines[start_line - 1 : start_line - 1 + max_lines])
    if len(content) > 24000:
        raise ValueError("Requested text is too large; request fewer lines")
    return {
        "content": content,
        "total_lines": len(lines),
        "start_line": start_line,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def factory_dot_status() -> dict:
    """Verify server-held Dot access. Does not reveal the token or claim work."""
    tasks = factory_dot_list_tasks()
    return {
        "identity": "dot",
        "project_id": 1,
        "role": "worker",
        "connected": True,
        "assigned_ready_task_ids": [t["id"] for t in tasks],
        "bridge": "MegaMCP -> Agent Kanban",
        "secrets_returned": False,
    }


def factory_dot_list_tasks() -> list[dict]:
    """List up to 20 ready tasks assigned to Dot, project 1, in Kanban priority order."""
    rows = _request("GET", "/api/tasks/available?project_id=1")
    return [t for t in rows if t.get("assigned_to") == "dot" and t.get("project_id") == 1][:20]


def factory_dot_get_task(task_id: int) -> dict:
    """Read one task assigned to Dot in project 1."""
    return _task(task_id)


def factory_dot_claim_task(task_id: int) -> dict:
    """Claim Dot's assigned task. Kanban enforces grants, schedules and conflicts."""
    _task(task_id)
    return _request("POST", f"/api/tasks/{task_id}/claim", payload={})


def factory_dot_heartbeat(task_id: int, notes: str = "") -> dict:
    """Renew Dot's active claim and record a bounded progress note."""
    _task(task_id, claimed=True)
    if len(notes) > 4000:
        raise ValueError("Progress note is too long")
    return _request("POST", f"/api/tasks/{task_id}/heartbeat", payload={"notes": notes})


def factory_dot_list_input_files(task_id: int, archive: str = "") -> list[dict]:
    """List ZIP input files. Use archive='research.zip' to inspect the nested research."""
    with _archive(task_id, archive) as z:
        return [{"path": i.filename, "bytes": i.file_size} for i in z.infolist()]


def factory_dot_read_input_file(
    task_id: int, path: str, archive: str = "", start_line: int = 1, max_lines: int = 160
) -> dict:
    """Read bounded UTF-8 text from the claimed input ZIP or its nested research.zip."""
    with _archive(task_id, archive) as z:
        try:
            info = z.getinfo(_relative(path))
        except KeyError:
            raise ValueError("Input file not found") from None
        if info.file_size > 1024 * 1024:
            raise ValueError("Text file exceeds 1 MiB")
        return _text(z.read(info), start_line, max_lines)


def factory_dot_write_output_file(
    task_id: int, path: str, content: str, expected_sha256: str | None = None
) -> dict:
    """Create/update one UTF-8 landing file (256 KiB max). For changes pass its previous hash."""
    work = _work(_task(task_id, claimed=True))
    files = work / "files"
    files.mkdir(exist_ok=True)
    target = _safe(files, path)
    data = content.encode("utf-8")
    if len(data) > MAX_TEXT:
        raise ValueError("Output file exceeds 256 KiB")
    if (work / "uploaded.json").exists():
        raise ValueError("This result was already published")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        if current != expected_sha256:
            raise ValueError("File changed; read it and pass expected_sha256")
    # Atomic replacement avoids leaving a truncated artifact if the process stops.
    import tempfile

    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            f.close()
            if target.is_symlink():
                raise ValueError("Output is a symlink")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def factory_dot_read_output_file(
    task_id: int, path: str, start_line: int = 1, max_lines: int = 160
) -> dict:
    """Read one of this claimed task's staged landing files and its hash."""
    work = _work(_task(task_id, claimed=True))
    file = _safe(work / "files", path)
    if not file.is_file() or file.stat().st_size > MAX_TEXT:
        raise ValueError("Output file unavailable")
    return _text(file.read_bytes(), start_line, max_lines)


def factory_dot_publish_result(task_id: int) -> dict:
    """ZIP the staged landing (index.html + README.md required) and PUT it to this task."""
    work = _work(_task(task_id, claimed=True))
    files = work / "files"
    if files.is_symlink() or files.resolve() != files.absolute() or not files.is_dir():
        raise ValueError("No staged landing files")
    paths = sorted(files.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("Symlinks are not allowed")
    paths = [p for p in paths if p.is_file()]
    names = {str(p.relative_to(files)) for p in paths}
    if not {"index.html", "README.md"} <= names:
        raise ValueError("index.html and README.md are required")
    if len(paths) > 512 or sum(p.stat().st_size for p in paths) > MAX_ZIP:
        raise ValueError("Landing exceeds file count/size limits")
    data = BytesIO()
    with ZipFile(data, "w", compression=ZIP_DEFLATED) as z:
        for p in paths:
            info = ZipInfo(str(p.relative_to(files)))
            info.compress_type = ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    body = data.getvalue()
    if len(body) > MAX_ZIP:
        raise ValueError("Result ZIP exceeds 10 MiB")
    digest = hashlib.sha256(body).hexdigest()
    receipt = work / "uploaded.json"
    if receipt.exists():
        if receipt.is_symlink():
            raise ValueError("Invalid upload receipt")
        saved = json.loads(receipt.read_text())
        if saved["sha256"] != digest:
            raise ValueError("Published result differs from staged files")
        return saved
    response = _request("PUT", f"/api/tasks/{task_id}/package/result", binary=body)
    saved = {
        "uploaded": True,
        "task_id": task_id,
        "sha256": digest,
        "bytes": len(body),
        "result_path": f"/api/tasks/{task_id}/package/result",
        "response": response,
    }
    fd = os.open(receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(saved, f)
    return saved


def factory_dot_submit_review(task_id: int, summary: str) -> dict:
    """After a confirmed upload, send Dot's task to review. No coordinator webhook needed."""
    task = _task(task_id)
    work = _work(task)
    receipt = work / "uploaded.json"
    if receipt.is_symlink() or not receipt.is_file():
        raise ValueError("Publish the ZIP first")
    saved = json.loads(receipt.read_text())
    if not saved.get("uploaded") or saved.get("task_id") != task_id:
        raise ValueError("Invalid upload receipt")
    if task.get("claimed_by") != "dot":
        raise ValueError("Task was not claimed by Dot")
    if task.get("status") == "review":
        return task
    _task(task_id, claimed=True)
    if not summary.strip() or len(summary) > 8000:
        raise ValueError("A bounded summary is required")
    return _request(
        "POST",
        f"/api/tasks/{task_id}/submit",
        payload={
            "summary_of_work": summary,
            "artifacts": [saved["result_path"]],
        },
    )


DOT_TOOLS = (
    factory_dot_status,
    factory_dot_list_tasks,
    factory_dot_get_task,
    factory_dot_claim_task,
    factory_dot_heartbeat,
    factory_dot_list_input_files,
    factory_dot_read_input_file,
    factory_dot_write_output_file,
    factory_dot_read_output_file,
    factory_dot_publish_result,
    factory_dot_submit_review,
)
DOT_TOOL_NAMES = frozenset(tool.__name__ for tool in DOT_TOOLS)


def register_dot_tools(server: FastMCP) -> None:
    """Opt in explicitly; existing transports/profiles keep their previous capabilities."""
    if os.getenv("FACTORY_DOT_BRIDGE_ENABLED", "false").lower() == "true":
        for tool in DOT_TOOLS:
            register_traced_tool(server, tool)
