"""Run the local MVP worker only when its scheduled Kanban queue has work."""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
PACKAGES = Path("/mnt/c/_mcp/muse-packages")


def pending(token):
    request = urllib.request.Request(
        "https://kanban-api.okehc.com/api/tasks/available?project_id=1",
        headers={"Authorization": "Bearer " + token, "User-Agent": "Kanban-Codex-Factory/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        tasks = json.load(response)
    return [
        t
        for t in tasks
        if t.get("assigned_to") == "codex"
        and t.get("metadata_payload", {}).get("factory_mode") == "sequential"
        and t["metadata_payload"].get("factory_step") == "mvp"
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Check queue and configuration; never invoke a model"
    )
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    if not args.check and not 16 <= now.hour < 18:
        print("outside_window")
        return
    token = os.environ.get("CODEX_KANBAN_TOKEN", "")
    if not token:
        raise RuntimeError("CODEX_KANBAN_TOKEN is required")
    state = Path.home() / ".local/state/agent-kanban"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / "codex-factory.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("already_running")
            return
        tasks = pending(token)
        print(json.dumps({"ready_task_ids": [t["id"] for t in tasks], "check_only": args.check}))
        if args.check or not tasks:
            return
        task = tasks[0]
        event = task["metadata_payload"]["event_id"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", event):
            raise ValueError("Invalid event id")
        workspace = PACKAGES / event / "04_mvp"
        if workspace.resolve() != workspace or not workspace.is_dir():
            raise ValueError("Invalid MVP workspace")
        executable = shutil.which("codex")
        if executable is None:
            raise RuntimeError("Codex CLI is not installed")
        prompt = (REPO / "docs/kanban-operation/sequential/codex.md").read_text()
        prompt += (
            "\n\nComienza por la tarjeta #"
            + str(task["id"])
            + " del proyecto 1. Mantén tus cambios dentro de su proyecto. No imprimas credenciales.\n"
        )
        command = [
            executable,
            "exec",
            "--approve-for-me",
            "--skip-git-repo-check",
            "-C",
            str(workspace),
            "-c",
            'mcp_servers.kanban_factory.url="https://kanban-api.okehc.com/mcp/"',
            "-c",
            'mcp_servers.kanban_factory.bearer_token_env_var="CODEX_KANBAN_TOKEN"',
            "-",
        ]
        log = state / ("codex-" + now.strftime("%Y%m%d-%H%M%S") + ".log")
        with log.open("x") as output:
            log.chmod(0o600)
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        print(json.dumps({"task_id": task["id"], "exit_code": result.returncode, "log": str(log)}))
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
