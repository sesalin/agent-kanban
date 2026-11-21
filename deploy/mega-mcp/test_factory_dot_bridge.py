"""Bounded contract tests for the Dot bridge, using a simulated Kanban backend."""

import base64
import copy
import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from app.mcp import factory_dot_bridge as dot
from mcp.server.fastmcp import FastMCP


def make_zip(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return stream.getvalue()


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_DOT_PACKAGES_ROOT", str(tmp_path))
    task = {
        "id": 42,
        "project_id": 1,
        "assigned_to": "dot",
        "claimed_by": None,
        "status": "ready",
        "metadata_payload": {
            "event_id": "event-1",
            "factory_step": "landing",
            "muse_zip": {
                "path": "event-1/03_specs",
                "input_file": "landing-input.zip",
                "output_path": "event-1/06_landing",
                "output_file": "landing.zip",
            },
        },
    }
    input_zip = make_zip(
        {
            "landing_spec.md": "Build a simple landing\nSecond line",
            "research.zip": make_zip({"hallazgos.md": "Verified research"}),
        }
    )
    calls = []

    def request(method, path, payload=None, binary=None, zip_response=False):
        calls.append((method, path))
        if path.startswith("/api/tasks/available"):
            return [
                copy.deepcopy(task),
                {"id": 99, "project_id": 1, "assigned_to": "brio"},
                {"id": 100, "project_id": 2, "assigned_to": "dot"},
            ]
        assert path.startswith("/api/tasks/42")
        if path.endswith("/claim"):
            task.update(status="in_progress", claimed_by="dot")
        elif path.endswith("/package/input"):
            assert task["status"] == "in_progress" and task["claimed_by"] == "dot"
            return input_zip
        elif method == "PUT":
            assert task["status"] == "in_progress"
            result = tmp_path / "event-1/06_landing/landing.zip"
            assert not result.exists() or task["metadata_payload"].get("validation_retries", 0) > 0
            result.write_bytes(binary)
            return {"bytes": len(binary), "path": "/api/tasks/42/package/result"}
        elif path.endswith("/submit"):
            assert (tmp_path / "event-1/06_landing/landing.zip").exists()
            task["status"] = "review"
        return copy.deepcopy(task)

    monkeypatch.setattr(dot, "_request", request)
    return task, calls, tmp_path


def result_file():
    return dot.OpenAIFile(
        download_url="https://files.oaiusercontent.com/result.zip?temporary=1",
        file_id="file-workspace",
        mime_type="application/zip",
        file_name="landing.zip",
    )


def test_workspace_zip_exchange_and_idempotent_publication(backend, monkeypatch):
    _task, calls, root = backend
    assert dot.factory_dot_status()["assigned_ready_task_ids"] == [42]
    with pytest.raises(ValueError, match="active Dot claim"):
        dot.factory_dot_download_input(42)
    dot.factory_dot_claim_task(42)
    contents = dot.factory_dot_download_input(42)
    assert contents[1].type == "resource"
    assert contents[1].resource.mimeType == "application/zip"
    assert str(contents[1].resource.uri) == "kanban-dot://tasks/42/landing-input.zip"
    with ZipFile(BytesIO(base64.b64decode(contents[1].resource.blob))) as z:
        assert "research.zip" in z.namelist()
    assert (
        dot.factory_dot_read_input_file(42, "hallazgos.md", archive="research.zip")["content"]
        == "Verified research"
    )
    dot.factory_dot_heartbeat(42, "Developing and testing in my workspace")
    # This completed archive represents a file built by Dot in its own workspace.
    body = make_zip(
        {
            "README.md": "Build and tests run by Dot",
            "package.json": "{}",
            "assets/image.bin": b"\x00\xff\x01",
            "src/index.js": "console.log('landing')",
        }
    )
    monkeypatch.setattr(dot, "_download_file", lambda file, data=body: data)
    receipt = dot.factory_dot_upload_result(42, result_file())
    assert dot.factory_dot_upload_result(42, result_file()) == receipt
    assert sum(method == "PUT" for method, _ in calls) == 1
    assert (root / "event-1/06_landing/landing.zip").read_bytes() == body
    assert not list(root.rglob("index.js"))  # No development files on the MCP host.
    assert dot.factory_dot_submit_review(42, "Built and tested locally")["status"] == "review"
    assert dot.factory_dot_submit_review(42, "Retry")["status"] == "review"
    assert sum(path.endswith("/submit") for _, path in calls) == 1
    _task.update(status="in_progress")
    _task["metadata_payload"]["validation_retries"] = 1
    corrected = make_zip({"README.md": "Corrected delivery", "index.html": "Fixed"})
    monkeypatch.setattr(dot, "_download_file", lambda file: corrected)
    retry = dot.factory_dot_upload_result(42, result_file())
    assert retry["validation_retries"] == 1
    assert (root / "event-1/06_landing/landing.zip").read_bytes() == corrected
    assert dot.factory_dot_upload_result(42, result_file()) == retry
    assert sum(method == "PUT" for method, _ in calls) == 2



def test_scope_paths_and_rejected_workspace_archives(backend, monkeypatch):
    task, _, root = backend
    for field, value in [("project_id", 2), ("assigned_to", "brio")]:
        old = task[field]
        task[field] = value
        with pytest.raises(ValueError, match="Only tasks assigned"):
            dot.factory_dot_get_task(42)
        task[field] = old
    dot.factory_dot_claim_task(42)
    with pytest.raises(ValueError, match="Publish the ZIP first"):
        dot.factory_dot_submit_review(42, "Too early")
    for path in ["../outside", "/outside", "a/../../outside", "a\\outside", "a/./outside"]:
        body = make_zip({"README.md": "Docs", path: "Rejected"})
        monkeypatch.setattr(dot, "_download_file", lambda file, data=body: data)
        with pytest.raises(ValueError):
            dot.factory_dot_upload_result(42, result_file())
    for body in [b"not-a-zip", make_zip({"index.html": "Missing docs"})]:
        monkeypatch.setattr(dot, "_download_file", lambda file, data=body: data)
        with pytest.raises(ValueError):
            dot.factory_dot_upload_result(42, result_file())
    target = root / "event-1/06_landing/.dot-transfer/task-42"
    target.rmdir()
    target.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        dot.factory_dot_download_input(42)
    target.unlink()
    task["metadata_payload"]["muse_zip"]["output_path"] = "other-event/06_landing"
    with pytest.raises(ValueError, match="canonical"):
        dot.factory_dot_download_input(42)
    assert not (root / "secret").exists()


@pytest.mark.asyncio
async def test_native_file_catalog_and_binary_resource(backend, monkeypatch):
    import hashlib

    from mcp.types import ListToolsRequest

    monkeypatch.delenv("FACTORY_DOT_BRIDGE_ENABLED", raising=False)
    off = FastMCP("off")
    dot.register_dot_tools(off)
    assert not off._tool_manager.list_tools()
    monkeypatch.setenv("FACTORY_DOT_BRIDGE_ENABLED", "true")
    on = FastMCP("on")
    dot.register_dot_tools(on)
    assert {t.name for t in on._tool_manager.list_tools()} == dot.DOT_TOOL_NAMES
    assert (
        not {
            "factory_dot_write_output_file",
            "factory_dot_read_output_file",
            "factory_dot_publish_result",
        }
        & dot.DOT_TOOL_NAMES
    )
    handler = on._mcp_server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    upload = next(t for t in result.root.tools if t.name == "factory_dot_upload_result")
    assert upload.meta == {"openai/fileParams": ["file"]}
    schema = upload.inputSchema["$defs"]["OpenAIFile"]
    assert set(schema["properties"]) == {"download_url", "file_id", "mime_type", "file_name"}
    assert set(schema["required"]) == {"download_url", "file_id"}
    dot.factory_dot_claim_task(42)
    linked = await on.call_tool("factory_dot_download_input", {"task_id": 42})
    if isinstance(linked, tuple):  # Newer SDK returns (content, structuredContent).
        linked = linked[0]
    resource = next(item.resource for item in linked if item.type == "resource")
    raw = base64.b64decode(resource.blob, validate=True)
    assert isinstance(raw, bytes)
    # The tool response itself carries the ZIP; a client need not resolve resources/read.
    assert (
        next(t for t in result.root.tools if t.name == "factory_dot_download_input").outputSchema
        is None
    )
    contents = await on.read_resource(resource.uri)
    assert next(iter(contents)).content == raw
    expected = json.loads(next(item.text for item in linked if item.type == "text"))
    assert hashlib.sha256(raw).hexdigest() == expected["sha256"]
    with ZipFile(BytesIO(raw)) as z:
        assert "research.zip" in z.namelist()


def test_file_reference_restrictions_and_binary_download(monkeypatch):
    from urllib.request import HTTPRedirectHandler

    for url in [
        "http://files.oaiusercontent.com/x",
        "https://127.0.0.1/x",
        "https://host.docker.internal/x",
        "https://files.oaiusercontent.com.attacker.invalid/x",
        "https://user:password@files.oaiusercontent.com/x",
    ]:
        with pytest.raises(ValueError, match="temporary HTTPS"):
            dot._download_file(dot.OpenAIFile(download_url=url, file_id="file-1"))
    body = make_zip({"README.md": "Ready", "image.bin": b"\x00\xff"})

    class Opener:
        def open(self, req, timeout):
            assert req.get_header("Authorization") is None
            assert timeout == 30
            return BytesIO(body)

    def build(handler):
        assert issubclass(handler, HTTPRedirectHandler)
        assert (
            handler().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid") is None
        )
        return Opener()

    monkeypatch.setattr("urllib.request.build_opener", build)
    assert dot._download_file(result_file()) == body
    monkeypatch.setattr(dot, "MAX_ZIP", 10)
    with pytest.raises(ValueError, match="10 MiB"):
        dot._download_file(result_file())


def test_request_restricts_target_and_redacts_secret(monkeypatch):
    from urllib.error import HTTPError
    from urllib.request import HTTPRedirectHandler

    monkeypatch.setenv("FACTORY_DOT_KANBAN_TOKEN", "private-test-dot-token")
    monkeypatch.setenv("FACTORY_DOT_KANBAN_URL", "https://attacker.invalid")
    with pytest.raises(ValueError, match="not allowed"):
        dot._request("GET", "/api/tasks/42")
    monkeypatch.setenv("FACTORY_DOT_KANBAN_URL", "http://host.docker.internal:7331")

    class Opener:
        def open(self, req, timeout):
            assert req.get_header("Authorization") == "Bearer private-test-dot-token"
            body = BytesIO(json.dumps({"detail": "Denied private-test-dot-token"}).encode())
            raise HTTPError(req.full_url, 403, "Denied", {}, body)

    def build(handler):
        assert issubclass(handler, HTTPRedirectHandler)
        assert (
            handler().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid") is None
        )
        return Opener()

    monkeypatch.setattr("urllib.request.build_opener", build)
    with pytest.raises(ValueError) as error:
        dot._request("GET", "/api/tasks/42")
    assert "403" in str(error.value) and "private-test-dot-token" not in str(error.value)
