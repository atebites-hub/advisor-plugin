"""Export a new, separate native Muse package; install and approve it separately."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__:
    from .export_bundle import prepare_export, write_export
else:
    from export_bundle import prepare_export, write_export


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def export_muse(destination: Path) -> Path:
    destination, contents, metadata = prepare_export(REPOSITORY_ROOT, destination)
    manifest = {
        "schemaVersion": 1,
        "name": "advisor",
        "displayName": "Advisor",
        "version": metadata["version"],
        "description": metadata["description"],
        "compat": {"source": "native", "manifestDir": ".muse-plugin"},
        "capabilities": {
            "skills": [
                {"id": name, "path": f"skills/{name}/SKILL.md", "enabledDefault": True}
                for name in ("advisor", "advisor-setup")
            ],
            "hooks": [{
                "id": "session-start", "event": "SessionStart",
                "command": ["uv", "run", "--script", "./advisor.py", "session-start"],
                "timeoutMs": 10000,
            }],
            "mcpServers": [{
                "id": "advisor", "transport": "stdio",
                "command": ["uv", "run", "--script", "./advisor.py", "serve"],
            }],
        },
    }

    contents[".muse-plugin/plugin.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return write_export(destination, contents)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Absolute path to a new directory with an existing parent.")
    args = parser.parse_args()
    try:
        destination = export_muse(args.destination)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Cannot export Advisor for Muse: {exc}\n"
              "Any newly created partial output is left in place. Use the bundle only after a successful export.",
              file=sys.stderr)
        return 1
    print(f"Exported Advisor for Muse to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
