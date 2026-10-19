"""Shared public-file boundary for the native Muse and Antigravity bundles."""

from __future__ import annotations

import json
from pathlib import Path


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


def prepare_export(repository: Path, destination: Path) -> tuple[Path, dict[str, bytes], dict]:
    repository = repository.resolve(strict=True)
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
    return destination, contents, metadata


def write_export(destination: Path, contents: dict[str, bytes]) -> Path:
    destination.mkdir()
    directories = {Path(relative).parent for relative in contents} - {Path(".")}
    for directory in sorted(directories):
        (destination / directory).mkdir(parents=True)
    # Callers append the native marker last; failed exports stay incomplete and are never removed.
    for relative, data in contents.items():
        with (destination / relative).open("xb") as output:
            output.write(data)
    return destination
