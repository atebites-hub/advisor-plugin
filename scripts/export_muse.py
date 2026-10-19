"""Export a new, separate native Muse package; install and approve it separately."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "advisor.py", "advisor.py.lock", "configuration.py", "session_context.py",
    "review_checkpoints.py", "usage_limits.py", "skills/advisor/SKILL.md",
    "skills/advisor-setup/SKILL.md",
)


def read_source(repository: Path, relative: str) -> bytes:
    path = repository
    for part in Path("plugins/advisor", relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Source contains a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"Source must be an existing regular file: {path}")
    return path.read_bytes()


def export_muse(destination: Path) -> Path:
    repository = REPOSITORY_ROOT.resolve(strict=True)
    if not destination.is_absolute():
        raise ValueError("Destination must be an absolute path to a new directory.")
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"Destination already exists: {destination}")
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("Destination parent must be an existing directory.")
    destination = parent / destination.name
    if destination.is_relative_to(repository) or repository.is_relative_to(destination):
        raise ValueError("Destination must not overlap the repository.")

    # Read the fixed inventory before reserving output; unrelated repository files never enter the bundle.
    contents = {relative: read_source(repository, relative) for relative in FILES}
    metadata = json.loads(read_source(repository, "plugin.json"))
    if not isinstance(metadata, dict) or any(
        not isinstance(metadata.get(key), str) or not metadata[key].strip()
        for key in ("version", "description")
    ):
        raise ValueError("Shared plugin manifest requires non-empty version and description strings.")
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

    destination.mkdir()
    for directory in (".muse-plugin", "skills", "skills/advisor", "skills/advisor-setup"):
        (destination / directory).mkdir()
    # Publish the native marker last; a failed export remains visibly incomplete and is never removed.
    contents[".muse-plugin/plugin.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    for relative, data in contents.items():
        with (destination / relative).open("xb") as output:
            output.write(data)
    return destination


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
