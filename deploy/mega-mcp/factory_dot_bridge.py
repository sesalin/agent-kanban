"""Task-scoped Dot access to Agent Kanban; credentials never cross the MCP boundary."""

import base64
import hashlib
import json
import os
import stat
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request
from zipfile import BadZipFile, ZipFile

from app.mcp.audit import audit_tool, register_traced_tool
from mcp.server.fastmcp import FastMCP
from mcp.types import BlobResourceContents, EmbeddedResource, TextContent
from pydantic import BaseModel, ConfigDict

MAX_ZIP = 10 * 1024 * 1024
MAX_INPUT = 32 * 1024 * 1024


class OpenAIFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    download_url: str
    file_id: str
    mime_type: str = ""
    file_name: str = ""


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
    work = _safe(root, event + "/06_landing/.dot-transfer/task-" + str(task["id"]))
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


def _input_zip(task_id: int) -> bytes:
    _work(_task(task_id, claimed=True))
    return _request("GET", f"/api/tasks/{task_id}/package/input", zip_response=True)


def factory_dot_download_input(task_id: int) -> list[TextContent | EmbeddedResource]:
    """Deliver the complete input ZIP inline as a binary attachment for Dot's workspace."""
    raw = _input_zip(task_id)
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "task_id": task_id,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "instruction": "Save the binary resource in your own workspace, verify its hash and work there.",
                }
            ),
        ),
        EmbeddedResource(
            type="resource",
            resource=BlobResourceContents(
                uri=f"kanban-dot://tasks/{task_id}/landing-input.zip",
                mimeType="application/zip",
                blob=base64.b64encode(raw).decode("ascii"),
            ),
        ),
    ]


def _download_file(file: OpenAIFile) -> bytes:
    url = urlsplit(file.download_url)
    host = (url.hostname or "").lower()
    if (
        url.scheme != "https"
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.fragment
        or not file.file_id.strip()
        or not (
            host.endswith((".oaiusercontent.com", ".chatgpt.com"))
            or host in ("oaiusercontent.com", "chatgpt.com")
        )
    ):
        raise ValueError("A temporary HTTPS file reference from ChatGPT is required")
    from urllib.request import HTTPRedirectHandler, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    # Never send the Kanban token to the file host or follow a supplied redirect.
    req = Request(file.download_url, headers={"User-Agent": "MegaMCP-Dot/1.0"})
    try:
        with build_opener(NoRedirect).open(req, timeout=30) as response:
            body = response.read(MAX_ZIP + 1)
    except HTTPError as error:
        raise ValueError(f"File download HTTP {error.code}; renew the file reference") from None
    except (URLError, TimeoutError):
        raise ValueError("File reference is unavailable; renew it") from None
    if len(body) > MAX_ZIP:
        raise ValueError("Result ZIP exceeds 10 MiB")
    return body


def _validate_result(body: bytes) -> None:
    try:
        with ZipFile(BytesIO(body)) as z:
            infos = z.infolist()
            if (
                not infos
                or len(infos) > 2000
                or sum(i.file_size for i in infos) > 100 * 1024 * 1024
            ):
                raise ValueError("ZIP exceeds member/uncompressed limits")
            names = []
            for info in infos:
                names.append(_relative(info.filename.rstrip("/")))
                if info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("Encrypted files and symlinks are not allowed")
            if len(set(names)) != len(names) or "README.md" not in z.namelist():
                raise ValueError("ZIP requires README.md and unique relative paths")
            if z.testzip() is not None:
                raise ValueError("ZIP checksum failed")
    except BadZipFile:
        raise ValueError("The result must be a valid ZIP") from None


def factory_dot_upload_result(task_id: int, file: OpenAIFile) -> dict:
    """Upload Dot's completed workspace ZIP as a native ChatGPT file; never a server-local path."""
    task = _task(task_id, claimed=True)
    work = _work(task)
    attempt = task.get("metadata_payload", {}).get("validation_retries", 0)
    body = _download_file(file)
    _validate_result(body)
    digest = hashlib.sha256(body).hexdigest()
    receipt = work / "uploaded.json"
    if receipt.exists():
        if receipt.is_symlink():
            raise ValueError("Invalid upload receipt")
        saved = json.loads(receipt.read_text())
        if saved.get("validation_retries", 0) == attempt:
            if saved["sha256"] != digest:
                raise ValueError("A different result was already published")
            return saved
    response = _request("PUT", f"/api/tasks/{task_id}/package/result", binary=body)
    saved = {
        "uploaded": True,
        "validation_retries": attempt,
        "task_id": task_id,
        "sha256": digest,
        "bytes": len(body),
        "result_path": f"/api/tasks/{task_id}/package/result",
        "response": response,
    }
    import tempfile
    with tempfile.NamedTemporaryFile(dir=work, mode="w", delete=False) as f:
        try:
            os.chmod(f.name, 0o600)
            json.dump(saved, f)
            f.close()
            os.replace(f.name, receipt)
        finally:
            Path(f.name).unlink(missing_ok=True)
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
    factory_dot_download_input,
    factory_dot_upload_result,
    factory_dot_submit_review,
)
DOT_TOOL_NAMES = frozenset(tool.__name__ for tool in DOT_TOOLS)


def register_dot_tools(server: FastMCP) -> None:
    """Opt in explicitly; existing transports/profiles keep their previous capabilities."""
    if os.getenv("FACTORY_DOT_BRIDGE_ENABLED", "false").lower() == "true":
        for tool in DOT_TOOLS:
            if tool is factory_dot_download_input:
                # Keep ZIP bytes out of duplicated model-visible structured JSON.
                server.add_tool(audit_tool(tool), structured_output=False)
            else:
                register_traced_tool(server, tool)

        @server.resource(
            "kanban-dot://tasks/{task_id}/landing-input.zip", mime_type="application/zip"
        )
        def input_resource(task_id: str) -> bytes:
            return _input_zip(_id(int(task_id)))

        # SDK 1.12 omits descriptor _meta; preserve the normal catalog and add file rewriting.
        @server._mcp_server.list_tools()
        async def tools_with_file_params():
            tools = await server.list_tools()
            for tool in tools:
                if tool.name == "factory_dot_upload_result":
                    tool.meta = {"openai/fileParams": ["file"]}
            return tools
