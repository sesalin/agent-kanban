"""Compatibility CLI for the same bounded operations exposed by the factory API."""

import argparse
import base64
import json
from pathlib import Path

from agent_kanban.factory_files import execute

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("input", "specs", "wakeup", "verify", "release"))
    parser.add_argument("payload_base64")
    arguments = parser.parse_args()
    document = json.loads(base64.b64decode(arguments.payload_base64, validate=True))
    print(
        json.dumps(
            execute(arguments.operation, document, tasks_root=Path.home() / "workspace_tasks"),
            ensure_ascii=False,
        )
    )
