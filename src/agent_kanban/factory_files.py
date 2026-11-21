"""Bounded, retry-safe file operations for the opportunity factory."""

import hashlib
import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, is_zipfile

ROOT = Path("/mnt/c/_mcp/muse-packages")
FOLDERS = (
    "01_input",
    "02_research",
    "03_specs",
    "04_mvp",
    "05_prospects",
    "06_landing",
    "07_release",
)


def inside(root: Path, path: str) -> Path:
    candidate = root / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()) or candidate.absolute() != resolved:
        raise ValueError("Path must stay inside the package root without symlinks")
    return resolved


def write_once(path: Path, content: bytes) -> None:
    """Retries accept identical files and preserve an existing different result."""
    if path.is_symlink() or path.parent.resolve() != path.parent.absolute():
        raise ValueError("Output must not traverse a symlink")
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Existing file differs: {path.name}")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            os.fchmod(stream.fileno(), 0o644)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise ValueError(f"Concurrent file differs: {path.name}")
        finally:
            temporary.unlink(missing_ok=True)


def execute(
    operation: str, payload: dict, root: Path = ROOT, tasks_root: Path | None = None
) -> dict:
    if operation not in {"input", "specs", "wakeup", "verify", "release"}:
        raise ValueError("Unknown operation")
    event_id = payload.get("event_id", "")
    if not isinstance(event_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", event_id
    ):
        raise ValueError("Invalid event_id")
    folder = inside(root, event_id)
    for name in FOLDERS:
        inside(root, f"{event_id}/{name}").mkdir(parents=True, exist_ok=True)

    if operation == "input":
        filename = payload.get("package_filename", "")
        if not isinstance(filename, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*\.zip", filename
        ):
            raise ValueError("Invalid package filename")
        package_path = Path(payload["package_path"])
        # Cards use the WSL path; the container mounts that same root elsewhere.
        if package_path.is_absolute() and package_path.is_relative_to(ROOT):
            package_path = package_path.relative_to(ROOT)
        source = inside(root, str(package_path / filename))
        if not is_zipfile(source):
            raise ValueError("Input must be an existing ZIP archive")
        content = source.read_bytes()
        write_once(folder / "01_input/paquete.zip", content)
        return {
            "event_id": event_id,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    if operation == "specs":
        if payload.get("decision") != "GO":
            raise ValueError("Only GO prepares specifications")
        research = inside(root, f"{event_id}/02_research/research.zip")
        if not is_zipfile(research):
            raise ValueError("Research must be an existing ZIP archive")
        for branch, prompt in (("mvp", "mvp"), ("prospection", "icp"), ("landing", "landing")):
            enabled = payload["branches"][f"run_{branch}"]
            if not isinstance(enabled, bool):
                raise TypeError("Branch flags must be booleans")
            if enabled and not isinstance(payload["specs"][f"{prompt}_prompt"], str):
                raise ValueError("An active branch needs a specification")
            if enabled and not payload["specs"][f"{prompt}_prompt"].strip():
                raise ValueError("An active branch needs a specification")
        write_once(
            folder / "03_specs/decision.json",
            json.dumps(payload, ensure_ascii=False, indent=2).encode(),
        )
        for branch, prompt in (("mvp", "mvp"), ("prospection", "icp"), ("landing", "landing")):
            if not payload["branches"][f"run_{branch}"]:
                continue
            text = payload["specs"][f"{prompt}_prompt"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("An active branch needs a specification")
            spec = folder / f"03_specs/{prompt}_spec.md"
            write_once(spec, text.encode())
            # Fixed ZIP timestamps make retries byte-for-byte reproducible.
            data = BytesIO()
            with ZipFile(data, "w") as archive:
                archive.writestr(ZipInfo(spec.name), spec.read_bytes())
                archive.writestr(ZipInfo("research.zip"), research.read_bytes())
                if branch == "landing":
                    from agent_kanban.config import get_settings
                    archive.writestr(ZipInfo("lead_config.json"), json.dumps({
                        "event_id": event_id, "project_slug": event_id,
                        "lead_endpoint": get_settings().public_lead_endpoint,
                    }, ensure_ascii=False, sort_keys=True))
            write_once(folder / f"03_specs/{branch}-input.zip", data.getvalue())
        return {"event_id": event_id, "specs_ready": True}

    if operation == "wakeup":
        task_id = str(payload.get("task_id", ""))
        if not task_id.isdecimal() or int(task_id) < 1:
            raise ValueError("Invalid MVP task id")
        if tasks_root is None:
            raise ValueError("Factory task directory is not configured")
        tasks = tasks_root
        tasks.mkdir(exist_ok=True)
        text = (
            f"# MVP {event_id}\n\nTarjeta Kanban: {task_id}\n"
            f"Especificación: {ROOT / event_id}/03_specs/mvp_spec.md\n"
            f"Salida: {ROOT / event_id}/04_mvp/mvp.zip\n"
            "Reclama la tarjeta, construye, verifica y entrega. Envía submit_for_review antes de WF4.\n"
            "WF4: https://anyo.okehc.com/webhook/factory/branch-done\n"
            "Al entregar, consulta list_my_tasks(project_id=1), filtra assigned_to=codex y continúa.\n"
        )
        write_once(tasks / f"TASK_MVP_{event_id}.md", text.encode())
        return {"event_id": event_id, "task_id": task_id, "file_ready": True}

    if operation == "verify":
        relative = payload["zip_path"]
        result = inside(root, relative)
        if not result.is_relative_to(folder) or not is_zipfile(result):
            raise ValueError("Missing or invalid ZIP for this opportunity")
        return {"event_id": event_id, "zip_path": relative, "bytes": result.stat().st_size}

    if operation == "release":
        text = payload.get("executive_summary")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Final summary is required")
        write_once(folder / "07_release/resumen_ejecutivo.md", text.encode())
        return {"event_id": event_id, "release_ready": True}
    raise ValueError("Unknown operation")
