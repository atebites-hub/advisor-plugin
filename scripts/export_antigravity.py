"""Export a new, separate native Antigravity package; install it separately."""

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


def export_antigravity(destination: Path) -> Path:
    destination, contents, metadata = prepare_export(REPOSITORY_ROOT, destination)
    manifests = {
        "mcp_config.json": {"mcpServers": {"advisor": {
            "command": "uv", "args": ["run", "--script", "./advisor.py", "serve"],
        }}},
        "hooks.json": {"advisor": {"SessionStart": [{
            "type": "command",
            "command": "uv run --script ./advisor.py session-start --hook-format antigravity",
            "timeout": 10,
        }]}},
        "plugin.json": {"name": "advisor", "description": metadata["description"]},
    }
    for relative, manifest in manifests.items():
        contents[relative] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return write_export(destination, contents)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="Absolute path to a new directory with an existing parent.")
    args = parser.parse_args()
    try:
        destination = export_antigravity(args.destination)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Cannot export Advisor for Antigravity: {exc}\n"
              "Any newly created partial output is left in place. Use the bundle only after a successful export.",
              file=sys.stderr)
        return 1
    print(f"Exported Advisor for Antigravity to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
