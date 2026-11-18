from io import BytesIO
from zipfile import ZipFile

import pytest

from agent_kanban.auth import generate_token, hash_token
from agent_kanban.config import get_settings
from agent_kanban.models import AgentProject, Project, Task, TaskStatus, Token, User


def make_zip(text: str) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("note.md", text)
    return stream.getvalue()


@pytest.mark.parametrize("output_path", [None, "research"])
async def test_claimed_worker_can_exchange_zip(
    session, authed_client, monkeypatch, tmp_path, output_path
):
    monkeypatch.setenv("MUSE_PACKAGES_ROOT", str(tmp_path))
    get_settings.cache_clear()

    project = Project(name="Kanban")
    session.add(project)
    await session.flush()
    task = Task(
        project_id=project.id,
        title="ZIP test",
        assigned_to="brio",
        status=TaskStatus.READY,
        metadata_payload={
            "muse_zip": {
                "path": "pilot",
                "input_file": "entrada.zip",
                "output_file": "hallazgos.zip",
                **({"output_path": output_path} if output_path else {}),
            }
        },
    )
    session.add(task)
    headers = {}
    admin = await session.get(User, 1)
    for name, role in (("brio", "worker"), ("otro", "worker"), ("bacha", "orchestrator")):
        token = generate_token()
        headers[name] = {"Authorization": f"Bearer {token}"}
        session.add(AgentProject(agent_name=name, project_id=project.id, role=role))
        session.add(
            Token(
                agent_name=name,
                token_hash=hash_token(token),
                token_prefix=token[:8],
                created_by_user_id=admin.id,
            )
        )
    await session.commit()
    authed_client.cookies.clear()

    folder = tmp_path / "pilot"
    folder.mkdir()
    if output_path:
        (tmp_path / output_path).mkdir()
    source = make_zip("input")
    (folder / "entrada.zip").write_bytes(source)
    api = f"/api/tasks/{task.id}"
    assert (
        await authed_client.get(f"{api}/package/input", headers=headers["brio"])
    ).status_code == 403
    assert (await authed_client.post(f"{api}/claim", headers=headers["brio"])).status_code == 200
    assert (
        await authed_client.get(f"{api}/package/input", headers=headers["otro"])
    ).status_code == 403
    assert (
        await authed_client.get(f"{api}/package/input", headers=headers["brio"])
    ).content == source

    upload_headers = {**headers["brio"], "Content-Type": "application/zip"}
    result_url = f"{api}/package/result"
    assert (
        await authed_client.put(result_url, headers=upload_headers, content=b"bogus")
    ).status_code == 422
    result = make_zip("output")
    assert (
        await authed_client.put(result_url, headers=upload_headers, content=result)
    ).status_code == 201
    assert (
        await authed_client.put(result_url, headers=upload_headers, content=source)
    ).status_code == 409
    assert (await authed_client.get(result_url, headers=headers["bacha"])).content == result
    assert (folder / "entrada.zip").read_bytes() == source
    assert (tmp_path / (output_path or "pilot") / "hallazgos.zip").read_bytes() == result
