from io import BytesIO
from zipfile import ZipFile

import pytest

from agent_kanban.auth import generate_token, hash_token
from agent_kanban.config import get_settings
from agent_kanban.factory_files import execute
from agent_kanban.models import AgentProject, Project, Token


def zip_bytes():
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr("data.md", "input")
    return data.getvalue()


def test_factory_files_preserve_inputs_and_bound_paths(tmp_path):
    root = tmp_path / "packages"
    root.mkdir()
    source = root / "original"
    source.mkdir()
    original = zip_bytes()
    (source / "source.zip").write_bytes(original)
    payload = {"event_id": "event-1", "package_path": str(source), "package_filename": "source.zip"}
    assert execute("input", payload, root)["bytes"] == len(original)
    execute("input", payload, root)
    event = root / "event-1"
    (event / "02_research/research.zip").write_bytes(original)
    specs = {
        "event_id": "event-1",
        "decision": "GO",
        "branches": {"run_mvp": True, "run_landing": False, "run_prospection": False},
        "specs": {"mvp_prompt": "Build this MVP"},
    }
    execute("specs", specs, root)
    package = (event / "03_specs/mvp-input.zip").read_bytes()
    execute("specs", specs, root)
    assert (event / "03_specs/mvp-input.zip").read_bytes() == package
    assert not (event / "03_specs/landing-input.zip").exists()
    with ZipFile(BytesIO(package)) as archive:
        assert archive.read("research.zip") == original
    tasks = tmp_path / "tasks"
    execute("wakeup", {"event_id": "event-1", "task_id": 42}, root, tasks)
    assert "Tarjeta Kanban: 42" in (tasks / "TASK_MVP_event-1.md").read_text()
    assert (
        "/mnt/c/_mcp/muse-packages/event-1/03_specs/mvp_spec.md"
        in (tasks / "TASK_MVP_event-1.md").read_text()
    )
    execute("release", {"event_id": "event-1", "executive_summary": "Done"}, root)
    with pytest.raises(ValueError):
        execute("release", {"event_id": "event-1", "executive_summary": "Overwrite"}, root)
    for bad in ["../outside", "/tmp", "event/other"]:
        with pytest.raises(ValueError):
            execute("input", {**payload, "event_id": bad}, root)
    for bad in ["../outside.zip", "/etc/passwd", "original/source.zip"]:
        with pytest.raises(ValueError):
            execute("verify", {"event_id": "event-1", "zip_path": bad}, root)
    (event / "02_research/link.zip").symlink_to(source / "source.zip")
    with pytest.raises(ValueError):
        execute("verify", {"event_id": "event-1", "zip_path": "event-1/02_research/link.zip"}, root)
    assert (source / "source.zip").read_bytes() == original


async def test_factory_api_requires_own_identity_and_project_grant(
    session, authed_client, monkeypatch, tmp_path
):
    monkeypatch.setenv("MUSE_PACKAGES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    project = Project(name="Factory")
    session.add(project)
    await session.flush()
    assert project.id == 1
    headers = {}
    for agent in ["n8n-radares", "nod"]:
        token = generate_token()
        session.add(
            Token(
                agent_name=agent,
                token_hash=hash_token(token),
                token_prefix=token[:8],
                created_by_user_id=1,
            )
        )
        headers[agent] = {"Authorization": f"Bearer {token}"}
    await session.commit()
    path = "/api/factory/files/release"
    body = {"event_id": "test", "executive_summary": "Completed"}
    assert (await authed_client.post(path, json=body)).status_code == 403
    authed_client.cookies.clear()
    assert (await authed_client.post(path, json=body)).status_code == 401
    for auth_headers in headers.values():
        assert (await authed_client.post(path, headers=auth_headers, json=body)).status_code == 403
    session.add(AgentProject(agent_name="n8n-radares", project_id=1, role="orchestrator"))
    session.add(AgentProject(agent_name="nod", project_id=1, role="orchestrator"))
    await session.commit()
    assert (await authed_client.post(path, headers=headers["nod"], json=body)).status_code == 403
    result = await authed_client.post(path, headers=headers["n8n-radares"], json=body)
    assert result.status_code == 200
    assert (tmp_path / "test/07_release/resumen_ejecutivo.md").read_text() == "Completed"
    assert (
        await authed_client.post(
            path, headers=headers["n8n-radares"], json={**body, "event_id": "../bad"}
        )
    ).status_code == 422
    assert (
        await authed_client.post(
            "/api/factory/files/unknown", headers=headers["n8n-radares"], json=body
        )
    ).status_code == 422
    get_settings.cache_clear()
