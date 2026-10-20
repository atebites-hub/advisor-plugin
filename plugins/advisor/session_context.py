"""Capture scoped native model input and selected workspace files without changing sources."""

from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
from typing import Callable


MAX_CONTEXT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_CONTEXT_FILES = 32
MAX_FILE_SOURCE_BYTES = 8 * 1024 * 1024
MAX_FILE_CONTEXT_BYTES = 8 * 1024 * 1024
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_HIDDEN_FIELDS = {"reasoning", "reasoningtext", "reasoningcontent", "thinking", "signature", "encryptedcontent", "providermetadata"}
_HIDDEN_TYPES = {"reasoning", "thinking", "redacted_thinking", "reasoning_content"}
_CREDENTIAL_KEY = re.compile(r"authorization|password|secret|credential|cookie|^token$|(?:api|access|auth|refresh)[_-]?(?:key|token)", re.I)


class ContextCaptureError(Exception):
    """The host's complete current semantic input could not be verified."""


class ContextUnavailableError(ContextCaptureError):
    """A verified current invocation lacks complete retained input."""

    def __init__(self, message: str):
        super().__init__(message)
        self.scope: dict[str, str] | None = None


def _read_file(path: Path, limit: int, *, tail: bool = False) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ContextCaptureError("Context source must be a regular file.")
        if info.st_size > limit:
            if not tail:
                raise ContextCaptureError("Context snapshot exceeds its size limit.")
            stream.seek(info.st_size - limit)
            stream.readline()
        return stream.read(limit + 1)


def _clean(value, redact: Callable[[str], str]):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_clean(item, redact) for item in value
                if not _hidden_block(item)]
    if isinstance(value, dict):
        if _hidden_block(value):
            return None
        result = {}
        for key, item in value.items():
            if re.sub(r"[^a-z]", "", key.lower()) in _HIDDEN_FIELDS:
                continue
            result[key] = "[REDACTED]" if _CREDENTIAL_KEY.search(key) else _clean(item, redact)
        return result
    return value


def _hidden_block(value) -> bool:
    return isinstance(value, dict) and isinstance(value.get("type"), str) and value["type"] in _HIDDEN_TYPES


def _clean_schema(value, redact: Callable[[str], str], credential: bool = False):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_clean_schema(item, redact, credential) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"properties", "patternProperties"} and isinstance(item, dict):
                result[key] = {name: _clean_schema(schema, redact, credential or bool(_CREDENTIAL_KEY.search(name)))
                               for name, schema in item.items()}
            elif credential and key in {"default", "const", "examples", "enum"}:
                result[key] = _redact_literal(item)
            else:
                result[key] = _clean_schema(item, redact, credential)
        return result
    return value


def _redact_literal(value):
    if isinstance(value, list):
        return [_redact_literal(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_literal(item) for key, item in value.items()}
    return None if value is None else "[REDACTED]"


def resolve_native_workspace(meta: dict, requested: Path | None, session_id: str) -> Path:
    native = Path(meta["workspace_path"])
    if not native.is_absolute() or not native.is_dir():
        raise ContextCaptureError("The native workspace is unavailable.")
    native = native.resolve()
    root = Path.home() / ".zcode" / "cli"
    database = Path(os.environ.get("ZCODE_SESSION_DB_PATH", os.environ.get("ZCODE_SESSION_DB", str(root / "db" / "db.sqlite")))).expanduser()
    if not database.is_file():
        raise ContextCaptureError("The native session index is unavailable.")
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT directory FROM session WHERE id = ?", (session_id,)).fetchone()
    if not row or not isinstance(row[0], str) or not Path(row[0]).is_absolute() or not Path(row[0]).is_dir():
        raise ContextCaptureError("The native session workspace is unavailable.")
    # ZCode reports a mutable cwd; the session index owns the workspace root.
    workspace = Path(row[0]).resolve()
    if not native.is_relative_to(workspace):
        raise ContextCaptureError("The native session does not belong to this workspace.")
    if requested is not None and (not requested.is_absolute() or requested.resolve() != workspace):
        raise ContextCaptureError("Requested workspace does not match the native session.")
    return workspace


def _status_message_array(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(message, dict)
        and isinstance(message.get("role"), str) and bool(message["role"]) for message in value)


def _recording_details(entry: dict) -> tuple[str, int, int]:
    """Classify one native record without reading another request or changing state."""
    unknown = ("unknown", 0, 0)
    try:
        request = entry.get("request") or {}
        messages, body = request.get("messages"), request.get("body") or {}
        tools = body.get("tools")
        if (not isinstance(entry.get("requestId"), str) or not entry["requestId"]
                or not _status_message_array(messages)
                or not isinstance(tools, (list, dict)) or not tools):
            return unknown
        keys = ("messagesKind", "messageCount", "messageOffset")
        kind, count, offset = (request.get(key) for key in keys)
        if any(key in request for key in keys):
            if (kind not in {"full", "delta", "tail"} or type(count) is not int or type(offset) is not int
                    or count <= 0 or offset < 0 or offset + len(messages) != count
                    or (kind == "full" and offset != 0)
                    or (kind != "full" and offset <= 0) or (kind == "tail" and not messages)):
                return unknown
            return "bounded", count, offset
        # Full mode retains canonical, SDK and body arrays without bounded metadata.
        metadata = ("sdkMessagesKind", "sdkMessageCount", "sdkMessageOffset",
                    "bodyMessagesKind", "bodyMessageCount", "bodyMessageOffset")
        if (any(key in request for key in metadata) or "modelIOReset" in entry or not messages
                or not _status_message_array(request.get("sdkMessages")) or not request["sdkMessages"]
                or not _status_message_array(body.get("messages")) or not body["messages"]):
            return unknown
        return "full_retention", len(messages), 0
    except (KeyError, TypeError, AttributeError):
        return unknown


def zcode_context_status(meta: dict, requested_workspace: Path | None = None) -> dict:
    """Report recording evidence for this status invocation, without copying context."""
    unknown = {"recording_mode": "unknown", "long_session_ready": False,
               "warning": "Current native recording could not be verified. Native consultations require "
                          "verified full_retention; check advisor_status in the current ZCode turn. Desktop full "
                          "recording requires user approval for app-wide unbounded logs; the tested standalone "
                          "CLI has no supported full-retention override."}
    try:
        native = meta.get("com.zcode/request-context") if isinstance(meta, dict) else None
        if not isinstance(native, dict):
            return unknown
        session_id, turn_id = native.get("session_id"), native.get("turn_id")
        if (not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id)
                or not isinstance(turn_id, str) or not turn_id
                or not isinstance(native.get("workspace_path"), str)):
            return unknown
        resolve_native_workspace(native, requested_workspace, session_id)
        root = Path.home() / ".zcode" / "cli"
        found = []
        for directory in ("rollout", "debug"):
            path = root / directory / f"model-io-{session_id}.jsonl"
            if not path.is_file():
                continue
            data = _read_file(path, MAX_SOURCE_BYTES, tail=True)
            if not data or not data.endswith(b"\n"):
                return unknown
            current = None
            for line in data.splitlines():
                entry = json.loads(line)
                if not isinstance(entry, dict) or entry.get("sessionId") != session_id:
                    return unknown
                if entry.get("type") == "model_io" and entry.get("turnId") == turn_id and entry.get("querySource") == "main_turn":
                    current = entry
            if current is not None:
                found.append((path, current))
        if len(found) != 1:
            return unknown
        path, entry = found[0]
        calls = (entry.get("response") or {}).get("toolCalls") or []
        status_calls = [call for call in calls if isinstance(call, dict)
                        and isinstance(call.get("name"), str)
                        and (call["name"] == "advisor_status" or call["name"].endswith("__advisor_status"))]
        if (len(status_calls) != 1 or not isinstance(status_calls[0].get("id"), str)
                or not status_calls[0]["id"] or status_calls[0].get("input") != {}):
            return unknown
        request = entry.get("request") or {}
        messages, body = request.get("messages"), request.get("body") or {}
        tools = body.get("tools")
        mode, count, offset = _recording_details(entry)
        if mode == "unknown":
            return unknown
        if mode == "bounded":
            warning = ("Native recording is bounded; native consultations require verified full_retention. Desktop requires "
                       "user-approved Settings > General > Keep complete model I/O (app-wide, unbounded logs, "
                       "including native reasoning). The tested standalone CLI has no supported full-retention "
                       "override; the Desktop setting does not enable it.")
        else:
            warning = ("Full native recording is observed for this request. Consultation still verifies exact "
                       "current input, coverage and size; this check does not recover discarded history or media.")
        return {"recording_mode": mode, "long_session_ready": mode == "full_retention", "warning": warning,
                "provenance": {"kind": "zcode_model_io", "source_file": str(path), "session_id": session_id,
                               "turn_id": turn_id, "request_id": entry["requestId"]},
                "counts": {"retained_messages": len(messages), "message_count": count,
                           "message_offset": offset, "tool_definitions": len(tools)}}
    except (ContextCaptureError, OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, sqlite3.Error):
        return unknown


def _current_record(path: Path, session_id: str, turn_id: str, consultation_request: dict | None) -> tuple[dict, list, str] | None:
    data = _read_file(path, MAX_SOURCE_BYTES, tail=True)
    if data and not data.endswith(b"\n"):
        return None
    previous = None
    current = None
    for line in data.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            continue
        entry = json.loads(line)
        if entry.get("sessionId") != session_id:
            raise ContextCaptureError("The model-input log belongs to another session.")
        if entry.get("type") != "model_io":
            continue
        request = entry.get("request") or {}
        messages = request.get("messages")
        kind = request.get("messagesKind", "full")
        offset = request.get("messageOffset", 0)
        count = request.get("messageCount", len(messages) if isinstance(messages, list) else None)
        if not isinstance(messages, list) or type(count) is not int or type(offset) is not int:
            previous = None
        elif kind == "full" and offset == 0 and len(messages) == count:
            previous = messages
        elif kind == "delta" and previous is not None and offset == len(previous) and offset + len(messages) == count:
            previous = previous + messages
        else:
            previous = None
        if entry.get("turnId") == turn_id and entry.get("querySource") == "main_turn":
            current = (entry, previous)
    if current is None:
        return None
    entry, messages = current
    calls = (entry.get("response") or {}).get("toolCalls") or []
    advisor_calls = [call for call in calls if isinstance(call, dict)
                     and isinstance(call.get("name"), str)
                     and (call["name"] == "consult_advisor" or call["name"].endswith("__consult_advisor"))]
    if consultation_request is not None:
        advisor_calls = [call for call in advisor_calls if isinstance(call.get("input"), dict)
                         and call["input"].get("request") == consultation_request]
    if not advisor_calls:
        return None
    if len(advisor_calls) != 1 or not isinstance(advisor_calls[0].get("id"), str) or not advisor_calls[0]["id"]:
        raise ContextCaptureError("The current Advisor call cannot be identified unambiguously.")
    if any(isinstance(call, dict) and call.get("name") in
           {"Write", "Edit", "MultiEdit", "ApplyPatch", "NotebookEdit"} for call in calls):
        raise ContextCaptureError("Finish file edits and checks before requesting a review in a separate tool batch.")
    if messages is None:
        request = entry.get("request") or {}
        retained = request.get("messages")
        kind, offset, count = (request.get(key) for key in ("messagesKind", "messageOffset", "messageCount"))
        if (kind not in {"delta", "tail"} or not isinstance(retained, list)
                or type(offset) is not int or type(count) is not int or offset <= 0
                or offset + len(retained) != count):
            raise ContextCaptureError("Current model input is incomplete; its retained-message metadata is invalid.")
        raise ContextUnavailableError(
            f"Current model input is incomplete: ZCode retained a {kind} record "
            f"(total_count={count}, offset={offset}, retained_count={len(retained)}) without a complete baseline. "
            "No provider job was created and no older prefix was reused. Do not substitute a manual CLI packet, "
            "older context, invented IDs, or another provider. Changing recording settings cannot repair this record. "
            "For future requests, Settings > General > Keep complete model I/O preserves full records, "
            "but applies app-wide and retains unbounded local logs."
        )
    body = (entry.get("request") or {}).get("body") or {}
    if not isinstance(body.get("tools"), (list, dict)) or not body["tools"]:
        raise ContextCaptureError("The current tool definitions were not retained.")
    if not body.get("system") and not any(isinstance(message, dict) and message.get("role") == "system" for message in messages):
        raise ContextCaptureError("The current system instructions were not retained.")
    mode, _, _ = _recording_details(entry)
    if mode != "full_retention":
        raise ContextCaptureError(
            f"Native recording mode is {mode}; every native ZCode consultation requires verified full_retention. "
            "No provider job or context snapshot was created. Desktop requires Settings > General > Keep complete model I/O "
            "for new requests; this user-approved app-wide setting stores unbounded local logs, including native reasoning. "
            "Do not change host settings or files without user approval. Re-check advisor_status, then consult again. "
            "Do not substitute a manual CLI packet, older context, invented IDs, or another provider. "
            "The tested standalone CLI has no supported full-retention override."
        )
    return entry, messages, advisor_calls[0]["id"]


def capture_zcode_context(meta: dict, requested_workspace: Path | None, state_dir: Path,
                          redact: Callable[[str], str], max_bytes: int = MAX_CONTEXT_BYTES,
                          consultation_request: dict | None = None) -> dict:
    """Bind only native request metadata; MCP transport IDs are never session IDs."""
    try:
        native = meta.get("com.zcode/request-context") if isinstance(meta, dict) else None
        if not isinstance(native, dict):
            raise ContextCaptureError("Native ZCode session metadata is unavailable.")
        session_id, turn_id, workspace_path = (native.get(key) for key in ("session_id", "turn_id", "workspace_path"))
        if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
            raise ContextCaptureError("Native ZCode session identity is invalid.")
        if not isinstance(turn_id, str) or not turn_id or not isinstance(workspace_path, str) or not workspace_path:
            raise ContextCaptureError("Native ZCode turn and workspace metadata are required.")
        workspace = resolve_native_workspace(native, requested_workspace, session_id)
        root = Path.home() / ".zcode" / "cli"
        selected = None
        deadline = time.monotonic() + 2
        while True:
            found = []
            unavailable = []
            for directory in ("rollout", "debug"):
                path = root / directory / f"model-io-{session_id}.jsonl"
                if path.is_file():
                    try:
                        record = _current_record(path, session_id, turn_id, consultation_request)
                    except ContextUnavailableError as exc:
                        unavailable.append(exc)
                        continue
                    if record is not None:
                        found.append((path, *record))
            if len(found) + len(unavailable) > 1:
                raise ContextCaptureError("Multiple current model-input sources match this session.")
            if unavailable:
                unavailable[0].scope = {"workspace": str(workspace), "session_id": session_id, "turn_id": turn_id}
                raise unavailable[0]
            if found:
                selected = found[0]
                break
            if time.monotonic() >= deadline:
                raise ContextCaptureError("The exact current Advisor model input is unavailable; no older request was substituted.")
            time.sleep(0.05)
        path, entry, messages, tool_call_id = selected
        request, response = entry["request"], entry.get("response") or {}
        body = request["body"]
        coverage = {
            "semantic_model_input": "complete",
            "native_wire_request": "not_available",
            "history_boundary": "current model input after host compaction; discarded earlier history is not recovered",
            "message_count": len(messages),
            "tool_definition_count": len(body["tools"]),
            "system_instructions": "native_body" if body.get("system") else "canonical_messages",
            "source_omissions": [],
            "excluded": ["hidden_reasoning", "credential_headers", "credential_values", "provider_metadata"],
        }
        provenance = {"kind": "zcode_model_io", "source_file": str(path),
                      "turn_id": turn_id, "request_id": entry.get("requestId"), "tool_call_id": tool_call_id}
        context = {"messages": _clean(messages, redact), "tools": _clean_schema(body["tools"], redact),
                   "system": _clean(body.get("system"), redact),
                   "assistant_response": _clean({key: response[key] for key in ("text", "toolCalls", "toolResults") if key in response}, redact)}
        if " omitted from model-io: " in json.dumps(context):
            coverage["semantic_model_input"] = "incomplete"
            coverage["source_omissions"] = ["binary_media"]
            coverage["excluded"].append("binary_media")
        payload = {"schema_version": 1, "binding": {"workspace": str(workspace), "host": "zcode", "session_id": session_id},
                   "coverage": coverage, "provenance": provenance, "context": context}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > max_bytes:
            raise ContextCaptureError("The full context exceeds the snapshot limit; nothing was silently truncated.")
        snapshot_id = hashlib.sha256(encoded).hexdigest()
        directory = Path(state_dir) / "contexts"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink():
            raise ContextCaptureError("Context storage must not be a symbolic link.")
        directory.chmod(0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
            temporary.replace(directory / f"{snapshot_id}.json")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return {"context_snapshot_id": snapshot_id, **payload["binding"], "coverage": coverage, "provenance": provenance}
    except ContextCaptureError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError, sqlite3.Error) as exc:
        raise ContextCaptureError("The native session context could not be read safely.") from exc


def load_context_snapshot(snapshot_id: str, workspace: Path | str, host: str,
                          session_id: str, state_dir: Path) -> dict:
    try:
        if not isinstance(snapshot_id, str) or not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
            raise ContextCaptureError("Invalid context snapshot identifier.")
        path = Path(state_dir) / "contexts" / f"{snapshot_id}.json"
        if path.parent.is_symlink():
            raise ContextCaptureError("Context storage must not be a symbolic link.")
        data = _read_file(path, MAX_CONTEXT_BYTES)
        if hashlib.sha256(data).hexdigest() != snapshot_id:
            raise ContextCaptureError("Context snapshot integrity check failed.")
        payload = json.loads(data)
        expected = {"workspace": str(Path(workspace).resolve()), "host": host, "session_id": session_id}
        if payload.get("schema_version") != 1 or payload.get("binding") != expected:
            raise ContextCaptureError("Context snapshot does not belong to this session and workspace.")
        return payload
    except ContextCaptureError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        raise ContextCaptureError("The private context snapshot is unavailable.") from exc


def _file_binding(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ContextCaptureError("File context requires a scoped request.")
    keys = ("workspace", "host", "session_id", "task_id")
    if any(not isinstance(request.get(key), str) or not request[key].strip()
           or "\0" in request[key] for key in keys):
        raise ContextCaptureError("File context requires workspace, host, session and task identities.")
    workspace = Path(request["workspace"])
    if not workspace.is_absolute() or ".." in workspace.parts:
        raise ContextCaptureError("File context requires an absolute workspace.")
    return {"workspace": str(workspace.resolve(strict=True)),
            **{key: request[key] for key in keys[1:]}}


def _selected_paths(value: object) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_CONTEXT_FILES:
        raise ContextCaptureError(f"Select between 1 and {MAX_CONTEXT_FILES} context files.")
    for path in value:
        if (not isinstance(path, str) or "\0" in path or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise ContextCaptureError("Context files must be explicit workspace-relative file paths.")
    if len(set(value)) != len(value):
        raise ContextCaptureError("Context files must not contain duplicate paths.")
    return sorted(value)


def _secure_file_primitives() -> None:
    if (not all(hasattr(os, name) for name in
                ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "fchmod", "getuid"))
            or any(function not in os.supports_dir_fd
                   for function in (os.open, os.mkdir, os.stat, os.link, os.unlink))
            or any(function not in os.supports_follow_symlinks for function in (os.stat, os.link))):
        raise ContextCaptureError("Secure selected-file snapshots are unsupported on this platform.")


def _file_directory(path: Path, *, create: bool = False) -> int:
    if not path.is_absolute() or ".." in path.parts:
        raise ContextCaptureError("File context directories must be absolute paths.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for name in path.parts[1:]:
            if create:
                try:
                    os.mkdir(name, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(name, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file_storage(state_dir: Path, *, create: bool) -> int:
    root = _file_directory(Path(state_dir), create=create)
    try:
        if create:
            try:
                os.mkdir("file-contexts", 0o700, dir_fd=root)
            except FileExistsError:
                pass
        descriptor = os.open("file-contexts", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=root)
    finally:
        os.close(root)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid():
            raise ContextCaptureError("File context storage must belong to the current user.")
        if create:
            os.fchmod(descriptor, 0o700)
        elif stat.S_IMODE(info.st_mode) & 0o077:
            raise ContextCaptureError("File context storage must be private.")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _file_identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stable_file(directory: int, name: str, limit: int, *, private: bool = False) -> bytes:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContextCaptureError("Context sources must be regular files.")
        if private and (before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) & 0o077):
            raise ContextCaptureError("File context snapshots must be private.")
        if before.st_size > limit:
            raise ContextCaptureError("File context exceeds its size limit; nothing was truncated.")
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ContextCaptureError("File context exceeds its size limit; nothing was truncated.")
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (size != before.st_size or _file_identity(before) != _file_identity(after)
                or _file_identity(before) != _file_identity(current)):
            raise ContextCaptureError("A context file changed while it was being captured.")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _selected_file(workspace: int, path: str, limit: int) -> bytes:
    directories = [os.dup(workspace)]
    try:
        parts = path.split("/")
        for name in parts[:-1]:
            directories.append(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                       dir_fd=directories[-1]))
        raw = _stable_file(directories[-1], parts[-1], limit)
        for index, name in enumerate(parts[:-1]):
            current = os.stat(name, dir_fd=directories[index], follow_symlinks=False)
            opened = os.fstat(directories[index + 1])
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ContextCaptureError("A context file directory changed during capture.")
        return raw
    finally:
        for descriptor in directories:
            os.close(descriptor)


def capture_file_context(request: dict, state_dir: Path, redact: Callable[[str], str]) -> str:
    """Freeze selected UTF-8 files, rejecting NUL text and detectable changes during each read."""
    try:
        _secure_file_primitives()
        binding = _file_binding(request)
        paths = _selected_paths(request.get("context_files"))
        workspace = _file_directory(Path(request["workspace"]))
        files = []
        remaining = MAX_FILE_SOURCE_BYTES
        try:
            for path in paths:
                raw = _selected_file(workspace, path, remaining)
                remaining -= len(raw)
                text = raw.decode("utf-8")
                if "\0" in text:
                    raise ContextCaptureError("Context files must be UTF-8 text without NUL bytes.")
                content = redact(text)
                if not isinstance(content, str) or "\0" in content:
                    raise ContextCaptureError("File context redaction must return UTF-8 text without NUL bytes.")
                encoded = content.encode("utf-8")
                files.append({"path": path, "content": content, "sha256": hashlib.sha256(encoded).hexdigest(),
                              "bytes": len(encoded), "redacted": content != text})
            current = _file_directory(Path(request["workspace"]))
            try:
                before, after = os.fstat(workspace), os.fstat(current)
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise ContextCaptureError("The workspace changed during file context capture.")
            finally:
                os.close(current)
        finally:
            os.close(workspace)
        payload = {"schema_version": 1, "binding": binding, "files": files}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_FILE_CONTEXT_BYTES:
            raise ContextCaptureError("The serialized file context exceeds its size limit; nothing was truncated.")
        snapshot_id = hashlib.sha256(encoded).hexdigest()
        directory = _file_storage(Path(state_dir), create=True)
        temporary = f".{snapshot_id}.{os.urandom(16).hex()}.tmp"
        created = False
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            created = True
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, f"{snapshot_id}.json", src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
            except FileExistsError:
                existing = _stable_file(directory, f"{snapshot_id}.json", MAX_FILE_CONTEXT_BYTES, private=True)
                if existing != encoded:
                    raise ContextCaptureError("An existing file context failed its integrity check.")
        finally:
            try:
                if created:
                    os.unlink(temporary, dir_fd=directory)
            finally:
                os.close(directory)
        return snapshot_id
    except ContextCaptureError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ContextCaptureError("The selected file context could not be captured safely.") from exc


def load_file_context(snapshot_id: str, request: dict, state_dir: Path) -> dict:
    """Load only the immutable selected-file snapshot belonging to this exact scope."""
    try:
        _secure_file_primitives()
        binding = _file_binding(request)
        if not isinstance(snapshot_id, str) or not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
            raise ContextCaptureError("Invalid file context snapshot identifier.")
        directory = _file_storage(Path(state_dir), create=False)
        try:
            data = _stable_file(directory, f"{snapshot_id}.json", MAX_FILE_CONTEXT_BYTES, private=True)
        finally:
            os.close(directory)
        if hashlib.sha256(data).hexdigest() != snapshot_id:
            raise ContextCaptureError("File context snapshot integrity check failed.")
        payload = json.loads(data)
        if (not isinstance(payload, dict) or set(payload) != {"schema_version", "binding", "files"}
                or type(payload["schema_version"]) is not int or payload["schema_version"] != 1
                or payload["binding"] != binding or not isinstance(payload["files"], list)):
            raise ContextCaptureError("File context does not belong to this session, task and workspace.")
        paths = _selected_paths([entry["path"] for entry in payload["files"]])
        if paths != [entry["path"] for entry in payload["files"]]:
            raise ContextCaptureError("File context paths are not in canonical order.")
        for entry in payload["files"]:
            if (set(entry) != {"path", "content", "sha256", "bytes", "redacted"}
                    or not isinstance(entry["content"], str) or "\0" in entry["content"]
                    or type(entry["bytes"]) is not int or type(entry["redacted"]) is not bool):
                raise ContextCaptureError("File context metadata is invalid.")
            encoded = entry["content"].encode("utf-8")
            if entry["bytes"] != len(encoded) or entry["sha256"] != hashlib.sha256(encoded).hexdigest():
                raise ContextCaptureError("File context content metadata failed its integrity check.")
        return payload
    except ContextCaptureError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ContextCaptureError("The private selected-file snapshot is unavailable.") from exc
