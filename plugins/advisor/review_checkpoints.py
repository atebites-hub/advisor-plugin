"""Native ZCode file-edit review checkpoints; hooks never invoke a provider."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from collections.abc import Callable

_NAMESPACE = "com.zcode/request-context"
_FILE_TOOLS = {"Write", "Edit", "ApplyPatch", "MultiEdit", "NotebookEdit"}
_PLAN_STAGES = {"before_plan", "after_plan", "before_task"}
_TERMINAL = {"completed", "failed", "interrupted"}


class CheckpointError(Exception):
    """A native review receipt or its scope could not be verified."""


def _scope(workspace, session_id, turn_id) -> tuple[str, str, str]:
    if any(not isinstance(value, str) or not value or "\x00" in value or len(value) > 4096
           for value in (workspace, session_id, turn_id)):
        raise CheckpointError("Native review checkpoint identity is incomplete.")
    path = Path(workspace)
    if not path.is_absolute() or not path.is_dir():
        raise CheckpointError("Native review checkpoint workspace is unavailable.")
    return str(path.resolve()), session_id, turn_id


def _job_scope(job: dict) -> tuple[str, str, str]:
    scope = job.get("scope")
    if (not isinstance(scope, dict) or scope.get("host") != "zcode"
            or not isinstance(job.get("context_transfer"), dict)
            or job["context_transfer"].get("mode") != "native_snapshot"):
        raise CheckpointError("Advisor job has no verified native review scope.")
    if (not isinstance(job.get("job_id"), str) or not re.fullmatch(r"[a-f0-9]{64}", job["job_id"])
            or type(job.get("submitted_at_ns")) is not int or job["submitted_at_ns"] <= 0
            or job.get("stage") not in _PLAN_STAGES | {"during_task"}):
        raise CheckpointError("Advisor job review metadata is incomplete.")
    return _scope(scope.get("workspace"), scope.get("session_id"), job.get("native_turn_id"))


def verify_job_scope(job_id: str, meta: dict, state_dir: Path) -> dict | None:
    """Verify native ownership before advice is exposed; manual calls have no receipt."""
    if not isinstance(meta, dict) or _NAMESPACE not in meta:
        return None
    from session_context import ContextCaptureError, resolve_native_workspace

    try:
        native = meta[_NAMESPACE]
        if not isinstance(native, dict):
            raise CheckpointError("Native review checkpoint metadata is invalid.")
        expected = _scope(native.get("workspace_path"), native.get("session_id"), native.get("turn_id"))
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{64}", job_id):
            raise CheckpointError("Invalid Advisor job identifier.")
        path = Path(state_dir) / "jobs" / job_id / "job.json"
        if path.parent.is_symlink() or path.parent.parent.is_symlink():
            raise CheckpointError("Advisor job state must not be a symbolic link.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65_536:
                raise CheckpointError("Advisor job metadata is invalid.")
            job = json.loads(stream.read(65_537))
        if not isinstance(job, dict) or job.get("job_id") != job_id:
            raise CheckpointError("Advisor job does not belong to this native workspace and session.")
        owner = _job_scope(job)
        workspace = resolve_native_workspace(native, Path(owner[0]), expected[1])
        if owner[:2] != (str(workspace), expected[1]):
            raise CheckpointError("Advisor job does not belong to this native workspace and session.")
        return job
    except (ContextCaptureError, sqlite3.Error, OSError, ValueError, TypeError) as exc:
        raise CheckpointError("Advisor cannot verify this job's native review scope.") from exc


@contextmanager
def _transaction(scope: tuple[str, str, str], state_dir: Path, *, dependencies: bool = False):
    directory = Path(state_dir) / "checkpoints"
    if directory.is_symlink():
        raise CheckpointError("Advisor checkpoint state must not be a symbolic link.")
    if dependencies:
        directory /= "dependencies"
        if directory.is_symlink():
            raise CheckpointError("Advisor dependency state must not be a symbolic link.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    identity = [scope[1]] if dependencies else [scope[0], "zcode", *scope[1:]]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    path = directory / (key + ".sqlite3")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise CheckpointError("Advisor checkpoint state is invalid.")
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    connection = sqlite3.connect(path, timeout=1)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if dependencies:
            connection.execute("CREATE TABLE IF NOT EXISTS binding(id INTEGER PRIMARY KEY CHECK(id=1), workspace TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS requirements(attempt_id TEXT PRIMARY KEY, job_id TEXT, paths TEXT NOT NULL, satisfied INTEGER NOT NULL DEFAULT 0)")
        else:
            connection.execute("CREATE TABLE IF NOT EXISTS reviews(job_id TEXT PRIMARY KEY, submitted_at_ns INTEGER NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS outstanding(job_id TEXT PRIMARY KEY, submitted_at_ns INTEGER NOT NULL, stage TEXT NOT NULL, watcher_id TEXT)")
            connection.execute("CREATE TABLE IF NOT EXISTS work(id INTEGER PRIMARY KEY CHECK(id=1), last_edit_ns INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS unavailable(id INTEGER PRIMARY KEY CHECK(id=1), started_at_ns INTEGER NOT NULL, last_edit_ns INTEGER NOT NULL)")
        yield connection
        connection.commit()
    finally:
        connection.close()


def normalize_dependent_paths(workspace, paths) -> list[str]:
    """Accept concrete workspace paths; retain lexical names and resolved aliases."""
    if isinstance(paths, list) and any(isinstance(value, str) and ("*" in value or "?" in value) for value in paths):
        raise CheckpointError("dependent_paths must contain concrete file or directory paths, without globs.")
    return _literal_paths(workspace, paths)


def _literal_paths(workspace, paths) -> list[str]:
    try:
        root = Path(workspace).resolve()
        if not isinstance(paths, list) or len(paths) > 128:
            raise CheckpointError("dependent_paths must be an explicit list of at most 128 concrete workspace paths.")
        normalized = set()
        for value in paths:
            if (not isinstance(value, str) or not value.strip() or len(value) > 4096
                    or any(character in value for character in "\x00\n\r")):
                raise CheckpointError("Advisor file paths must be nonempty concrete paths without control characters.")
            path = Path(value)
            path = path if path.is_absolute() else root / path
            lexical, resolved = Path(os.path.abspath(path)), path.resolve()
            if not resolved.is_relative_to(root):
                raise CheckpointError("Advisor file paths must resolve within the consultation workspace.")
            normalized.add(str(resolved))
            if lexical.is_relative_to(root):
                normalized.add(str(lexical))
        if len(normalized) > 128:
            raise CheckpointError("dependent_paths exceeds 128 paths after resolving aliases.")
        return sorted(normalized)
    except (OSError, RuntimeError) as exc:
        raise CheckpointError("Advisor cannot resolve the workspace file paths safely.") from exc


def _dependency_binding(connection, workspace: str) -> None:
    row = connection.execute("SELECT workspace FROM binding WHERE id=1").fetchone()
    if not row or row[0] != workspace:
        raise CheckpointError("Advisor dependency state does not belong to this native workspace.")


def begin_dependencies(scope: dict, dependent_paths: list, attempt_id: str, state_dir: Path) -> None:
    """Arm a verified native attempt before provider launch, even if no job follows."""
    try:
        identity = _scope(scope.get("workspace"), scope.get("session_id"), scope.get("turn_id"))
        paths = normalize_dependent_paths(identity[0], dependent_paths)
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[a-f0-9]{32,64}", attempt_id):
            raise CheckpointError("Advisor dependency attempt identity is invalid.")
        with _transaction(identity, state_dir, dependencies=True) as connection:
            connection.execute("INSERT OR IGNORE INTO binding VALUES (1,?)", (identity[0],))
            _dependency_binding(connection, identity[0])
            encoded = json.dumps(paths)
            row = connection.execute("SELECT paths FROM requirements WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row and row[0] != encoded:
                raise CheckpointError("Advisor dependency declaration changed after the attempt began.")
            connection.execute("INSERT OR IGNORE INTO requirements(attempt_id,paths) VALUES (?,?)", (attempt_id, encoded))
    except (OSError, sqlite3.Error) as exc:
        raise CheckpointError("Advisor cannot save the native dependency declaration.") from exc


def attach_dependencies(scope: dict, attempt_id: str, job: dict, state_dir: Path) -> None:
    """Bind an armed attempt to its real job without clearing the obligation."""
    try:
        identity = _scope(scope.get("workspace"), scope.get("session_id"), scope.get("turn_id"))
        if _job_scope(job) != identity:
            raise CheckpointError("Advisor dependency job does not match the native attempt.")
        with _transaction(identity, state_dir, dependencies=True) as connection:
            _dependency_binding(connection, identity[0])
            row = connection.execute("SELECT job_id,paths,satisfied FROM requirements WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row and row[0] == job["job_id"] and row[2] == 1:
                if row[1] != json.dumps(job.get("dependent_paths")):
                    raise CheckpointError("Advisor job does not match the satisfied dependency declaration.")
                return
            paths = normalize_dependent_paths(identity[0], job.get("dependent_paths"))
            if not row or row[1] != json.dumps(paths) or row[0] not in (None, job["job_id"]):
                raise CheckpointError("Advisor job does not match the armed dependency declaration.")
            connection.execute("UPDATE requirements SET job_id=? WHERE attempt_id=?", (job["job_id"], attempt_id))
    except (OSError, sqlite3.Error) as exc:
        raise CheckpointError("Advisor cannot attach the native dependency job.") from exc


def _dependency_file(scope, state_dir: Path) -> Path:
    key = hashlib.sha256(json.dumps([scope[1]]).encode()).hexdigest()
    return Path(state_dir) / "checkpoints" / "dependencies" / (key + ".sqlite3")


def _has_dependencies(scope, state_dir: Path) -> bool:
    path = _dependency_file(scope, state_dir)
    if path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise CheckpointError("Advisor dependency state must not be a symbolic link.")
    return path.exists() or path.is_symlink()


def _dependency_scope(scope, state_dir: Path) -> tuple[tuple[str, str, str], list[str]]:
    if not _has_dependencies(scope, state_dir):
        return scope, []
    with _transaction(scope, state_dir, dependencies=True) as connection:
        row = connection.execute("SELECT workspace FROM binding WHERE id=1").fetchone()
        if not row or not Path(scope[0]).is_relative_to(row[0]):
            raise CheckpointError("Native hook working directory is outside the registered Advisor workspace.")
        paths = set()
        for (encoded,) in connection.execute("SELECT paths FROM requirements WHERE satisfied=0"):
            saved = json.loads(encoded)
            if normalize_dependent_paths(row[0], saved) != saved:
                raise CheckpointError("Advisor dependency paths changed or could not be verified.")
            paths.update(saved)
        return (row[0], *scope[1:]), sorted(paths)


def _mutation_paths(tool: str, inputs, cwd: str, workspace: str) -> list[str]:
    # shortcut: shell/delegated writes remain policy-only until the host exposes their file targets.
    if not isinstance(inputs, dict):
        raise CheckpointError("Advisor cannot identify this mutation's file paths.")
    if tool == "ApplyPatch":
        patch = inputs.get("patch_text")
        if not isinstance(patch, str) or not patch.startswith("*** Begin Patch\n") or not patch.rstrip().endswith("*** End Patch"):
            raise CheckpointError("Advisor cannot identify this patch's file paths.")
        values = re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", patch, re.MULTILINE)
    elif tool == "NotebookEdit":
        values = [inputs.get("notebook_path")]
    else:
        values = [inputs.get("file_path")]
    if not values:
        raise CheckpointError("Advisor cannot identify this mutation's file paths.")
    absolute = [str(Path(value) if Path(value).is_absolute() else Path(cwd) / value)
                if isinstance(value, str) else value for value in values]
    return _literal_paths(workspace, absolute)


def register_review(job: dict, state_dir: Path) -> None:
    """Remember native submissions without recording retrieval or completing review."""
    try:
        scope = _job_scope(job)
        expected = (job["submitted_at_ns"], job["stage"])
        with _transaction(scope, state_dir) as connection:
            for table in ("reviews", "outstanding"):
                previous = connection.execute(f"SELECT submitted_at_ns, stage FROM {table} WHERE job_id=?", (job["job_id"],)).fetchone()
                if previous and previous != expected:
                    raise CheckpointError("Advisor job review metadata changed after registration.")
                if previous and table == "reviews":
                    return
            connection.execute("INSERT OR IGNORE INTO outstanding(job_id,submitted_at_ns,stage) VALUES (?,?,?)", (job["job_id"], *expected))
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
        raise CheckpointError("Advisor cannot save the native review submission.") from exc


def record_review(job: dict, result: dict, state_dir: Path) -> None:
    """Called only by native MCP retrieval, never by submit or internal polling."""
    try:
        if result.get("status") not in _TERMINAL:
            return
        if result["status"] == "completed" and (not isinstance(result.get("advice"), str) or not result["advice"].strip()):
            raise CheckpointError("Completed Advisor review has no usable advice; dependent work remains blocked.")
        scope = _job_scope(job)
        if result.get("job_id", job["job_id"]) != job["job_id"]:
            raise CheckpointError("Advisor result does not match the verified job.")
        if (result["status"] == "completed" and _has_dependencies(scope, state_dir)
                and result.get("job_id") != job["job_id"]):
            raise CheckpointError("Advisor result does not identify the dependency's exact job.")
        with _transaction(scope, state_dir) as connection:
            release = result["status"] == "completed" and _has_dependencies(scope, state_dir)
            if release:
                path = _dependency_file(scope, state_dir)
                if path.is_symlink():
                    raise CheckpointError("Advisor dependency state must not be a symbolic link.")
                connection.execute("ATTACH DATABASE ? AS dependencies", (str(path),))
                binding = connection.execute("SELECT workspace FROM dependencies.binding WHERE id=1").fetchone()
                if not binding or binding[0] != scope[0]:
                    raise CheckpointError("Advisor dependency state does not belong to this native workspace.")
            for table in ("reviews", "outstanding"):
                previous = connection.execute(f"SELECT submitted_at_ns, stage FROM {table} WHERE job_id=?", (job["job_id"],)).fetchone()
                if previous and previous != (job["submitted_at_ns"], job["stage"]):
                    raise CheckpointError("Advisor job review metadata changed after retrieval.")
            connection.execute("INSERT INTO reviews VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=CASE WHEN reviews.status='completed' THEN reviews.status ELSE excluded.status END",
                               (job["job_id"], job["submitted_at_ns"], result["status"], job["stage"]))
            connection.execute("DELETE FROM outstanding WHERE job_id=?", (job["job_id"],))
            if release:
                connection.execute("UPDATE dependencies.requirements SET satisfied=1 WHERE job_id=?", (job["job_id"],))
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
        raise CheckpointError("Advisor cannot save the native review receipt.") from exc


def record_unavailable_review(scope: dict, started_at_ns: int, state_dir: Path) -> None:
    """Record only a capture adapter's verified failed attempt, never a receipt."""
    if not isinstance(scope, dict) or type(started_at_ns) is not int or started_at_ns <= 0:
        raise CheckpointError("Unavailable native review attempt metadata is invalid.")
    identity = _scope(scope.get("workspace"), scope.get("session_id"), scope.get("turn_id"))
    try:
        with _transaction(identity, state_dir) as connection:
            row = connection.execute("SELECT last_edit_ns FROM work WHERE id=1").fetchone()
            if not row or started_at_ns <= row[0]:
                return
            connection.execute("INSERT INTO unavailable VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET started_at_ns=excluded.started_at_ns, last_edit_ns=excluded.last_edit_ns WHERE excluded.started_at_ns > unavailable.started_at_ns",
                               (started_at_ns, row[0]))
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
        raise CheckpointError("Advisor cannot save the unavailable native review attempt.") from exc


def _alias(event: dict, snake: str, camel: str):
    if snake in event and camel in event and event[snake] != event[camel]:
        raise CheckpointError("Native review checkpoint identity is ambiguous.")
    return event.get(snake, event.get(camel))


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": reason, "additionalContext": reason}}


def _outstanding(connection, read_status: Callable[[str], dict] | None) -> list[tuple[str, str]]:
    jobs = []
    for (job_id,) in connection.execute("SELECT job_id FROM outstanding ORDER BY submitted_at_ns, job_id"):
        try:
            result = read_status(job_id) if read_status else {"status": "pending"}
            if (not isinstance(result, dict) or result.get("status") not in _TERMINAL | {"pending"}
                    or result.get("job_id", job_id) != job_id):
                raise CheckpointError("Advisor job status could not be verified.")
            jobs.append((job_id, result["status"]))
        except Exception as exc:
            raise CheckpointError("Advisor job status could not be verified; use read_advice to check the existing job.") from exc
    return jobs


def _job_ids(jobs: list[tuple[str, str]]) -> str:
    return ", ".join(job_id for job_id, _ in jobs[:5]) + (" (and more)" if len(jobs) > 5 else "")


def _record_watch(event: dict, connection, outstanding: list[tuple[str, str]], watch_command: Callable[[str], str] | None) -> None:
    if not watch_command or _alias(event, "tool_name", "toolName") != "Bash":
        return
    inputs = _alias(event, "tool_input", "toolInput")
    response = _alias(event, "tool_response", "toolResponse")
    if (not isinstance(inputs, dict) or inputs.get("run_in_background") is not True
            or not isinstance(response, dict) or response.get("status") != "backgrounded"
            or response.get("interrupted") is not False):
        return
    task_id = response.get("backgroundTaskId")
    if not isinstance(task_id, str) or not task_id or "\x00" in task_id or len(task_id) > 4096:
        return
    for job_id, _ in outstanding:
        if inputs.get("command") == watch_command(job_id):
            connection.execute("UPDATE outstanding SET watcher_id=COALESCE(watcher_id,?) WHERE job_id=?", (task_id, job_id))


def review_checkpoint(event: dict, state_dir: Path, *, read_status: Callable[[str], dict] | None = None,
                      watch_command: Callable[[str], str] | None = None) -> dict:
    """Block declared dependent mutations and remind agents to retrieve advice."""
    name = event.get("hook_event_name", event.get("hookEventName")) if isinstance(event, dict) else None
    tool = event.get("tool_name", event.get("toolName")) if isinstance(event, dict) else None
    if name == "PreToolUse" and not isinstance(tool, str):
        return _deny("Advisor cannot verify the file-edit tool identity. Report the checkpoint failure before editing.")
    if name not in {"Stop", "PostToolUse", "PostToolUseFailure"} and not (name == "PreToolUse" and tool in _FILE_TOOLS):
        return {}
    try:
        scope = _scope(event.get("cwd"), _alias(event, "session_id", "sessionId"), _alias(event, "turn_id", "turnId"))
        scope, blocked_paths = _dependency_scope(scope, state_dir)
        dependency_message = ("Advisor advice is still required for these declared paths: " + ", ".join(blocked_paths[:5]) +
                              ". Failed, interrupted, unavailable, or unread advice does not release this work. "
                              "Continue only independent work; report the blocker instead of proceeding on your own judgment.") if blocked_paths else ""
        if name == "PreToolUse" and blocked_paths:
            targets = _mutation_paths(tool, _alias(event, "tool_input", "toolInput"), event["cwd"], scope[0])
            if any(Path(target).is_relative_to(blocked) or Path(blocked).is_relative_to(target)
                   for target in targets for blocked in blocked_paths):
                return _deny(dependency_message)
        with _transaction(scope, state_dir) as connection:
            reviews = connection.execute("SELECT submitted_at_ns, status, stage FROM reviews").fetchall()
            submissions = connection.execute("SELECT submitted_at_ns, stage FROM outstanding").fetchall()
            outstanding = _outstanding(connection, read_status)
            row = connection.execute("SELECT last_edit_ns FROM work WHERE id=1").fetchone()
            last_edit = row[0] if row else 0
            if name in {"PostToolUse", "PostToolUseFailure"}:
                if name == "PostToolUse":
                    _record_watch(event, connection, outstanding, watch_command)
                ready = [job for job in outstanding if job[1] in _TERMINAL]
                if not ready:
                    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": dependency_message}} if dependency_message else {}
                return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                        "Advisor jobs have finished and remain unread: " + _job_ids(ready) +
                        ". Call read_advice for these existing jobs now. Evaluate completed advice before dependent work; report failures without automatic retry or fallback."}}
            if name == "PreToolUse":
                # Mark admission before execution: a failed tool may already have changed a file.
                latest_submission = max([submitted for submitted, _, _ in reviews] + [submitted for submitted, _ in submissions], default=0)
                edited = max(time.time_ns(), last_edit + 1, latest_submission + 1)
                connection.execute("INSERT INTO work VALUES (1,?) ON CONFLICT(id) DO UPDATE SET last_edit_ns=excluded.last_edit_ns", (edited,))
                connection.execute("DELETE FROM unavailable")
                if outstanding:
                    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                            "Outstanding Advisor jobs: " + _job_ids(outstanding) +
                            ". Continue only independent work. Retrieve and evaluate completed advice before the decision or implementation that depends on it."}}
                return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": dependency_message}} if dependency_message else {}
            if outstanding:
                watcher_count = connection.execute("SELECT COUNT(*) FROM outstanding WHERE watcher_id IS NOT NULL").fetchone()[0]
                if read_status is not None and all(status == "pending" for _, status in outstanding) and watcher_count == len(outstanding):
                    return {"systemMessage": "Advisor jobs are still pending and native background completion watchers are running: " + _job_ids(outstanding) +
                            ". This task is waiting and remains incomplete. Yield until the background completion notification, then call read_advice for the original jobs and evaluate the advice before dependent work or claiming completion."}
                return {"decision": "block", "reason": "Advisor jobs remain pending or unread: " + _job_ids(outstanding) +
                        ". Call read_advice for these existing jobs. While pending, continue independent work or use the native background completion watcher; do not declare the task done. Evaluate completed advice before dependent work; do not resubmit to poll."}
            if dependency_message:
                return {"systemMessage": dependency_message + " This task remains incomplete."}
            planned = [status for _, status, stage in reviews if stage in _PLAN_STAGES]
            if not planned:
                return {}
            fresh = [status for submitted, status, _ in reviews if submitted > last_edit]
            if "completed" in fresh:
                return {}
            if any(status in {"failed", "interrupted"} for status in fresh):
                return {"systemMessage": "The fresh final Advisor review failed or was interrupted. Report that final review is incomplete and explain the failure; do not retry or switch providers automatically."}
            if "completed" not in planned:
                return {"systemMessage": "The early Advisor review failed or was interrupted. Report the review as incomplete and explain the failure; do not retry, switch providers automatically, or perform work that required the missing advice."}
            if not last_edit:
                return {}
            unavailable = connection.execute("SELECT started_at_ns, last_edit_ns FROM unavailable WHERE id=1").fetchone()
            if unavailable and unavailable[1] == last_edit and unavailable[0] > last_edit:
                return {"systemMessage": "The final Advisor review is incomplete because native context capture was unavailable. No Advisor job or provider was started for that attempt. Report the incomplete review; do not retry, invoke an advising CLI directly, reread older advice to bypass the checkpoint, or fall back to another provider."}
            # shortcut: ZCode permits only three Stop continuations; this is a review guardrail.
            return {"decision": "block", "reason": "Before finishing this planned task, save and check the deliverable, submit a new final Advisor consultation after the latest edit, and retrieve its completed advice with read_advice. Rereading older advice does not satisfy final review."}
    except (CheckpointError, OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
        message = "Advisor checkpoint state is unavailable. Report that review could not be verified; do not claim the review completed or retry automatically."
        if name == "PreToolUse":
            return _deny(message)
        if name in {"PostToolUse", "PostToolUseFailure"}:
            return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": message + " Check existing jobs with read_advice."}}
        return {"systemMessage": message}
