"""User-owned Advisor profiles and the interactive CLI setup wizard."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile


DEFAULT_ADVISORS = {
    "claude": {"enabled": True, "model": "claude-opus-5-5", "effort": "max"},
    "codex": {"enabled": True, "model": "gpt-6.1-sol", "effort": "max"},
    # Opt-in: an omitted profile stays disabled so upgrades do not start a new advisor.
    "cursor": {"enabled": False, "model": "claude-opus-5-5-high", "effort": "high"},
}
LEGACY_PROFILES = {"claude": "claude-opus-5-5", "codex": "gpt-6.1-sol"}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MAX_CONFIG_BYTES = 16_384
_CURSOR_EFFORT = re.compile(r"-(?:(?P<effort>low|medium|high|xhigh|max)|extra-high)(?:-fast)?$")


class ConfigurationError(ValueError):
    """A configuration cannot be read, validated, or safely saved."""


def config_path(path: Path | None = None) -> Path:
    selected = path if path is not None else os.environ.get("ADVISOR_CONFIG")
    return Path(selected).expanduser() if selected else Path.home() / ".config/advisor/config.json"


def cursor_model_effort(model: str) -> str | None:
    """Return the effort encoded by a Cursor catalog id, such as claude-opus-5-5-high."""
    if not isinstance(model, str):
        return None
    match = _CURSOR_EFFORT.search(model)
    if match is None:
        return None
    return match.group("effort") or "xhigh"


def validate_cursor_profile(model: str, effort: str) -> None:
    encoded = cursor_model_effort(model)
    if encoded is None:
        raise ConfigurationError("Cursor model ids must encode an effort suffix, for example claude-opus-5-5-high.")
    if encoded != effort:
        raise ConfigurationError(f"Cursor effort must match the model id suffix ({encoded}).")


def validate_model(provider: str, model: str) -> None:
    if not isinstance(provider, str) or provider not in DEFAULT_ADVISORS:
        raise ConfigurationError("Advisor provider must be claude, codex, or cursor.")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
        raise ConfigurationError("Advisor model must be a safe identifier of 1 to 128 characters.")
    if provider == "claude" and not re.fullmatch(r"claude-[a-z0-9][a-z0-9.-]*", model):
        raise ConfigurationError("Claude models must use an explicit claude- model identifier, not an alias.")
    if provider == "codex" and model.lower().startswith("claude-"):
        raise ConfigurationError("Codex cannot use a Claude model identifier.")


def resolved_advisors(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ConfigurationError("Advisor configuration must be a JSON object.")
    supplied = config.get("advisors", {})
    if not isinstance(supplied, dict) or any(name not in DEFAULT_ADVISORS for name in supplied):
        raise ConfigurationError("advisors must be an object containing only claude, codex, and cursor profiles.")
    profiles = {name: dict(profile) for name, profile in DEFAULT_ADVISORS.items()}
    for name, values in supplied.items():
        if not isinstance(values, dict) or any(key not in ("enabled", "model", "effort") for key in values):
            raise ConfigurationError(f"advisors.{name} accepts only enabled, model, and effort.")
        profiles[name].update(values)
    for name, profile in profiles.items():
        if type(profile["enabled"]) is not bool:
            raise ConfigurationError(f"advisors.{name}.enabled must be a boolean.")
        validate_model(name, profile["model"])
        if not isinstance(profile["effort"], str) or profile["effort"] not in EFFORTS:
            raise ConfigurationError(f"advisors.{name}.effort must be one of: {', '.join(EFFORTS)}.")
        if name == "cursor":
            validate_cursor_profile(profile["model"], profile["effort"])
    return profiles


def _validate(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ConfigurationError("Advisor configuration must be a JSON object.")
    if "provider" in config or "model" in config:
        name = config.get("provider")
        if not isinstance(name, str) or name not in LEGACY_PROFILES or config.get("model") != LEGACY_PROFILES[name]:
            raise ConfigurationError("Configuration must select one of the two fixed advisor profiles.")
    for key, default in (("idle_timeout_seconds", 1200), ("max_consults_per_task", 5)):
        value = config.get(key, default)
        if type(value) is not int or not 1 <= value <= 3600:
            raise ConfigurationError(f"{key} must be an integer from 1 to 3600.")
    if "timeout_seconds" in config:
        value = config["timeout_seconds"]
        if type(value) is not int or not 1 <= value <= 3600:
            raise ConfigurationError("timeout_seconds must be an integer from 1 to 3600 when supplied.")
    if "usage_fallback" in config and type(config["usage_fallback"]) is not bool:
        raise ConfigurationError("usage_fallback must be a boolean.")
    resolved_advisors(config)
    return config


def _parse(data: bytes) -> dict:
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigurationError("Advisor configuration is too large.")
    try:
        config = json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise ConfigurationError("Cannot read Advisor configuration as JSON.") from exc
    return _validate(config)


def _identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode, info.st_uid)


def _user_id() -> int:
    getuid = getattr(os, "getuid", None)
    if not callable(getuid):
        raise ConfigurationError("Guided setup requires POSIX ownership checks; configure the JSON file manually on this platform.")
    return getuid()


def _snapshot(path: Path, *, private: bool = False) -> tuple[bytes, tuple] | None:
    try:
        info = path.lstat() if private else path.stat()
        if not stat.S_ISREG(info.st_mode) or (private and info.st_uid != _user_id()):
            raise ConfigurationError("Advisor configuration must be a user-owned regular file; symlinks are not allowed when saving."
                                     if private else "Cannot read Advisor configuration as JSON.")
        descriptor = os.open(path, os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0) if private else 0))
        with os.fdopen(descriptor, "rb") as stream:
            if _identity(os.fstat(stream.fileno())) != _identity(info):
                raise ConfigurationError("Advisor configuration changed while being read.")
            data = stream.read(MAX_CONFIG_BYTES + 1)
            if _identity(os.fstat(stream.fileno())) != _identity(info):
                raise ConfigurationError("Advisor configuration changed while being read.")
        return data, _identity(info)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigurationError("Cannot read Advisor configuration as JSON.") from exc


def load_config(path: Path | None = None) -> dict:
    selected = config_path(path)
    snapshot = _snapshot(selected)
    if snapshot is None:
        if path is not None or os.environ.get("ADVISOR_CONFIG"):
            raise ConfigurationError(f"Advisor configuration does not exist: {selected}")
        return {}
    return _parse(snapshot[0])


def _save(path: Path, config: dict, baseline: tuple[bytes, tuple] | None) -> None:
    data = (json.dumps(_validate(config), indent=2) + "\n").encode()
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigurationError("Advisor configuration is too large.")
    try:
        owner = _user_id()
        missing = []
        parent = path.parent
        while not parent.exists() and not parent.is_symlink():
            missing.append(parent)
            parent = parent.parent
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != owner:
            raise ConfigurationError("Advisor configuration directory must be a user-owned directory, not a symlink.")
        # System-owned aliases such as macOS /var are outside the user's configuration path.
        for ancestor in (parent, *parent.parents):
            info = ancestor.lstat()
            if stat.S_ISLNK(info.st_mode) and info.st_uid == owner:
                raise ConfigurationError("Advisor configuration path must not contain user-owned symlinks.")
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
        if _snapshot(path, private=True) != baseline:
            raise ConfigurationError("Advisor configuration changed during setup; rerun configure.")
        descriptor, temporary = tempfile.mkstemp(prefix=".advisor-config-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if _snapshot(path, private=True) != baseline:
                raise ConfigurationError("Advisor configuration changed during setup; rerun configure.")
            if baseline is None:
                try:
                    os.link(temporary, path, follow_symlinks=False)
                except FileExistsError as exc:
                    raise ConfigurationError("Advisor configuration changed during setup; rerun configure.") from exc
            else:
                os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except OSError as exc:
        raise ConfigurationError("Cannot safely save Advisor configuration.") from exc


def _yes_no(prompt: str, default: bool) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes", "n", "no"):
            return answer in ("y", "yes")
        print("Enter yes or no.")


def configure(path: Path | None = None) -> int:
    _user_id()
    selected = config_path(path)
    baseline = _snapshot(selected, private=True)
    config = _parse(baseline[0]) if baseline else {}
    profiles = resolved_advisors(config)
    try:
        for name, profile in profiles.items():
            profile["enabled"] = _yes_no(f"Enable {name}? [{'Y/n' if profile['enabled'] else 'y/N'}]: ", profile["enabled"])
            if not profile["enabled"]:
                continue
            while True:
                model = input(f"{name} model [{profile['model']}]: ").strip() or profile["model"]
                try:
                    validate_model(name, model)
                except ConfigurationError as exc:
                    print(exc)
                else:
                    profile["model"] = model
                    break
            while True:
                effort = input(f"{name} effort ({', '.join(EFFORTS)}) [{profile['effort']}]: ").strip() or profile["effort"]
                if effort in EFFORTS:
                    profile["effort"] = effort
                    break
                print(f"Choose one of: {', '.join(EFFORTS)}.")
        for name, profile in profiles.items():
            print(f"{name}: {'enabled' if profile['enabled'] else 'disabled'}, model={profile['model']}, effort={profile['effort']}")
        if not _yes_no("Save advisor settings? [y/N]: ", False):
            return 0
    except EOFError:
        return 0
    _save(selected, {**config, "advisors": profiles}, baseline)
    return 0
