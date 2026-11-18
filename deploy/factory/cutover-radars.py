"""Switch MegaMCP's radar destinations after the anyo receivers are published."""

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit


def cutover(apply: bool) -> None:
    configuration = Path("/mnt/c/_mcp/mega-mcp/.env")
    private = Path.home() / ".config/agent-kanban"
    credentials = dict(
        line.split("=", 1) for line in (private / "n8n-radares.env").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    token = credentials["N8N_RADARES_HEADER_KANBAN_TOKEN"]
    replacements = {
        "RADAR_WEBHOOK_URL": "https://anyo.okehc.com/webhook/radar-events",
        "RADAR_ANALYSIS_NOTIFY_URL": "https://anyo.okehc.com/webhook/radar-analysis-notify",
        "RADAR_GOBIERNO_NOTIFY_URL": "https://anyo.okehc.com/webhook/radar-analysis-notify",
        "RADAR_WEBHOOK_TOKEN": token,
        "RADAR_ANALYSIS_NOTIFY_TOKEN": token,
        "RADAR_GOBIERNO_NOTIFY_TOKEN": token,
    }
    lines = configuration.read_text().splitlines()
    updated = []
    seen = set()
    for line in lines:
        key, _, old = line.partition("=")
        if key in replacements:
            if key in seen:
                raise ValueError(f"Duplicate configuration key: {key}")
            seen.add(key)
            if key.endswith("_URL"):
                print(f"{key}: {urlsplit(old.strip().strip(chr(34))).hostname} -> anyo.okehc.com")
            updated.append(f"{key}={replacements[key]}")
        else:
            updated.append(line)
    updated.extend(f"{key}={value}" for key, value in replacements.items() if key not in seen)
    if apply:
        backup = private / "mega-mcp-before-anyo.env"
        if not backup.exists():
            with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
                stream.write(configuration.read_text())
        configuration.write_text("\n".join(updated) + "\n")
        print("Configuration updated. Recreate the MegaMCP service to load the new environment.")
    else:
        print("Preview only. Publish and verify both receiving workflows before using --apply.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    cutover(parser.parse_args().apply)
