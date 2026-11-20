"""Bounded contract tests for the Dot bridge, using a simulated Kanban backend."""

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
            assert not result.exists()
            result.write_bytes(binary)
            return {"bytes": len(binary), "path": "/api/tasks/42/package/result"}
        elif path.endswith("/submit"):
            assert (tmp_path / "event-1/06_landing/landing.zip").exists()
            task["status"] = "review"
        return copy.deepcopy(task)

    monkeypatch.setattr(dot, "_request", request)
    return task, calls, tmp_path


def test_complete_landing_exchange_and_idempotent_publication(backend):
    _task, calls, root = backend
    assert dot.factory_dot_status()["assigned_ready_task_ids"] == [42]
    with pytest.raises(ValueError, match="active Dot claim"):
        dot.factory_dot_write_output_file(42, "index.html", "Too early")
    dot.factory_dot_claim_task(42)
    assert (
        dot.factory_dot_read_input_file(42, "landing_spec.md", max_lines=1)["content"]
        == "Build a simple landing"
    )
    assert (
        dot.factory_dot_read_input_file(42, "hallazgos.md", archive="research.zip")["content"]
        == "Verified research"
    )
    dot.factory_dot_heartbeat(42, "Working")
    dot.factory_dot_write_output_file(42, "index.html", "<h1>Landing</h1>")
    dot.factory_dot_write_output_file(42, "assets/style.css", "body {color: black}")
    dot.factory_dot_write_output_file(42, "README.md", "Open index.html")
    receipt = dot.factory_dot_publish_result(42)
    assert dot.factory_dot_publish_result(42) == receipt
    assert sum(method == "PUT" for method, _ in calls) == 1
    with ZipFile(root / "event-1/06_landing/landing.zip") as z:
        assert set(z.namelist()) == {"index.html", "assets/style.css", "README.md"}
    assert dot.factory_dot_submit_review(42, "Built and checked")["status"] == "review"
    assert dot.factory_dot_submit_review(42, "Retry")["status"] == "review"
    assert sum(path.endswith("/submit") for _, path in calls) == 1


def test_scope_and_paths_and_symlinks(backend):
    task, _, root = backend
    for field, value in [("project_id", 2), ("assigned_to", "brio")]:
        old = task[field]
        task[field] = value
        with pytest.raises(ValueError, match="Only tasks assigned"):
            dot.factory_dot_get_task(42)
        task[field] = old
    dot.factory_dot_claim_task(42)
    for path in ["../outside", "/outside", "a/../../outside", "a\\outside", "a/./outside"]:
        with pytest.raises(ValueError):
            dot.factory_dot_write_output_file(42, path, "No")
    dot.factory_dot_write_output_file(42, "index.html", "Index")
    work = root / "event-1/06_landing/.dot-work/task-42/files"
    (work / "escape").symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        dot.factory_dot_write_output_file(42, "escape/secret", "No")
    task["metadata_payload"]["muse_zip"]["output_path"] = "other-event/06_landing"
    with pytest.raises(ValueError, match="canonical"):
        dot.factory_dot_read_output_file(42, "index.html")
    assert not (root / "secret").exists()


def test_update_hash_limits_and_publish_before_submit(backend):
    dot.factory_dot_claim_task(42)
    original = dot.factory_dot_write_output_file(42, "index.html", "First")
    assert dot.factory_dot_write_output_file(42, "index.html", "First") == original
    with pytest.raises(ValueError, match="File changed"):
        dot.factory_dot_write_output_file(42, "index.html", "Changed")
    sha = dot.factory_dot_read_output_file(42, "index.html")["sha256"]
    dot.factory_dot_write_output_file(42, "index.html", "Changed", expected_sha256=sha)
    with pytest.raises(ValueError, match="256 KiB"):
        dot.factory_dot_write_output_file(42, "large.txt", "x" * (dot.MAX_TEXT + 1))
    with pytest.raises(ValueError, match="README"):
        dot.factory_dot_publish_result(42)
    with pytest.raises(ValueError, match="Publish the ZIP first"):
        dot.factory_dot_submit_review(42, "Too early")


def test_opt_in_registration(monkeypatch):
    monkeypatch.delenv("FACTORY_DOT_BRIDGE_ENABLED", raising=False)
    off = FastMCP("off")
    dot.register_dot_tools(off)
    assert not off._tool_manager.list_tools()
    monkeypatch.setenv("FACTORY_DOT_BRIDGE_ENABLED", "true")
    on = FastMCP("on")
    dot.register_dot_tools(on)
    assert {t.name for t in on._tool_manager.list_tools()} == dot.DOT_TOOL_NAMES


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
