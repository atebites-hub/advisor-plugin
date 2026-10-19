"""Verify consumed-usage failures without decoding stored conversation bodies.

Codex exec drops typed error causes. Its own append-only rollout must corroborate
the terminal message; unsupported storage layouts or incomplete capture are unknown.
"""

import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import uuid

from configuration import EFFORTS


MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 16384
MAX_DEPTH = 64
MAX_DIRECTORY_ENTRIES = 4096
VERIFY_SECONDS = 2.0
BOUNDARY_BYTES = 4096
MODELS = {"claude": "claude-opus-5-5", "codex": "gpt-6.1-sol"}
_MODEL_SELECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_CLAUDE_MODEL = re.compile(r"claude-[a-z0-9][a-z0-9.-]*")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_STRING_END = re.compile(r'["\\\x00-\x1f]')
_TIME = r"(?:[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)"
_RESET = re.compile(r"(?:(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
                    r"([1-9]|[12][0-9]|3[01])(st|nd|rd|th), ([0-9]{4}) )?(" + _TIME + r")")
_USAGE_PREFIXES = (
    ("You’ve hit your usage limit.", " Try again"),
    ("You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
     "visit https://chatgpt.com/settings/usage to purchase more credits", " or try again"),
    ("You’ve hit your usage limit. Visit https://chatgpt.com/settings/usage to purchase more credits",
     " or try again"),
    ("You’ve hit your usage limit. To get more access now, send a request to your admin", " or try again"),
    ("You’ve hit your usage limit. Upgrade to Plus to continue using Codex "
     "(https://chatgpt.com/explore/plus),", " or try again"),
)
_CREDITS = {
    "Your workspace is out of credits. Add credits to continue.",
    "Your workspace is out of credits. Ask your workspace owner to refill in order to continue.",
}
# Audited formatter and rollout schema: openai/codex rust-v0.162.1,
# codex-rs/protocol/src/error.rs:701-849 and protocol.rs:2173-2221.


class _Unknown(Exception):
    pass


class _Budget:
    def __init__(self, deadline):
        now = time.monotonic()
        self.until = now + VERIFY_SECONDS
        if deadline is not None:
            if type(deadline) not in (int, float) or not math.isfinite(deadline):
                raise _Unknown
            self.until = min(self.until, deadline)
        self.check()

    def check(self):
        if time.monotonic() >= self.until:
            raise _Unknown


class _JSON:
    """Validate JSON spans; only explicitly requested metadata reaches json.loads."""

    def __init__(self, raw: bytes, budget: _Budget):
        self.text = raw.decode("utf-8", errors="strict")
        self.budget = budget
        self.steps = 0
        end = self._value(self._ws(0), 0)
        if self._ws(end) != len(self.text):
            raise _Unknown

    def _ws(self, index):
        while index < len(self.text) and self.text[index] in " \t\r\n":
            index += 1
            if index % 4096 == 0:
                self.budget.check()
        return index

    def _string(self, index):
        if index >= len(self.text) or self.text[index] != '"':
            raise _Unknown
        index += 1
        while True:
            match = _STRING_END.search(self.text, index)
            self.budget.check()
            if match is None:
                raise _Unknown
            index = match.start()
            char = self.text[index]
            if char == '"':
                return index + 1
            if char != "\\" or index + 1 >= len(self.text):
                raise _Unknown
            escape = self.text[index + 1]
            if escape == "u":
                digits = self.text[index + 2:index + 6]
                if len(digits) != 4 or any(c not in "0123456789abcdefABCDEF" for c in digits):
                    raise _Unknown
                index += 6
            elif escape in '"\\/bfnrt':
                index += 2
            else:
                raise _Unknown

    def _value(self, index, depth):
        self.steps += 1
        if self.steps % 256 == 0:
            self.budget.check()
        if index >= len(self.text):
            raise _Unknown
        char = self.text[index]
        if char == '"':
            return self._string(index)
        if char in "{[":
            if depth >= MAX_DEPTH:
                raise _Unknown
            end_char = "}" if char == "{" else "]"
            index = self._ws(index + 1)
            if index < len(self.text) and self.text[index] == end_char:
                return index + 1
            while True:
                if char == "{":
                    index = self._ws(self._string(index))
                    if index >= len(self.text) or self.text[index] != ":":
                        raise _Unknown
                    index = self._ws(index + 1)
                index = self._ws(self._value(index, depth + 1))
                if index >= len(self.text):
                    raise _Unknown
                if self.text[index] == end_char:
                    return index + 1
                if self.text[index] != ",":
                    raise _Unknown
                index = self._ws(index + 1)
        for token in ("true", "false", "null"):
            if self.text.startswith(token, index):
                return index + len(token)
        match = _NUMBER.match(self.text, index)
        if match is None:
            raise _Unknown
        return match.end()

    def object(self, span=None):
        start, end = span if span is not None else (self._ws(0), len(self.text))
        if self.text[start:start + 1] != "{":
            raise _Unknown
        index = self._ws(start + 1)
        fields = {}
        while self.text[index] != "}":
            key_end = self._string(index)
            if key_end - index > 256:
                raise _Unknown
            key = json.loads(self.text[index:key_end])
            if key in fields:
                raise _Unknown
            index = self._ws(key_end)
            if self.text[index] != ":":
                raise _Unknown
            index = self._ws(index + 1)
            value_end = self._value(index, 0)
            fields[key] = (index, value_end)
            if len(fields) > 4096:
                raise _Unknown
            index = self._ws(value_end)
            if self.text[index] == ",":
                index = self._ws(index + 1)
        if self._ws(index + 1) != self._ws(end):
            raise _Unknown
        return fields

    def scalar(self, fields, key, expected=str):
        if key not in fields:
            return None
        start, end = fields[key]
        if end - start > 4096 or self.text[start:start + 1] in "{[":
            raise _Unknown
        value = json.loads(self.text[start:end])
        if value is None:
            return None
        if type(value) is not expected:
            raise _Unknown
        return value


def _records(raw: bytes, budget: _Budget, *, require_lf=False, initial_count=0):
    if len(raw) > MAX_SCAN_BYTES or (require_lf and raw and not raw.endswith(b"\n")):
        raise _Unknown
    offset = 0
    count = initial_count
    while offset < len(raw):
        budget.check()
        end = raw.find(b"\n", offset)
        end = len(raw) if end < 0 else end + 1
        count += 1
        if count > MAX_RECORDS or end - offset > MAX_RECORD_BYTES:
            raise _Unknown
        line = raw[offset:end]
        offset = end
        if not line.strip() or (require_lf and not line.endswith(b"\n")):
            raise _Unknown
        yield _JSON(line, budget)


def _usage_message(message):
    if not isinstance(message, str):
        return False
    if message in _CREDITS:
        return True
    for prefix, suffix in _USAGE_PREFIXES:
        if message == prefix + suffix + " later.":
            return True
        beginning = prefix + suffix + " at "
        if not message.startswith(beginning) or not message.endswith("."):
            continue
        match = _RESET.fullmatch(message[len(beginning):-1])
        if match is None:
            continue
        month, day, ordinal, year, _ = match.groups()
        if month is None:
            return True
        day = int(day)
        expected = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        if ordinal != expected:
            continue
        try:
            dt.date(int(year), ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
                                "Oct", "Nov", "Dec").index(month) + 1, day)
        except ValueError:
            continue
        return True
    return False


def _thread_date(session_id):
    if not isinstance(session_id, str):
        raise _Unknown
    identity = uuid.UUID(session_id)
    if str(identity) != session_id or identity.version != 7:
        raise _Unknown
    return dt.datetime.fromtimestamp((identity.int >> 80) / 1000, dt.timezone.utc).date()


def _safe_directory(path: Path):
    if (not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "pread", "getuid"))
            or os.open not in os.supports_dir_fd or os.scandir not in os.supports_fd):
        raise _Unknown
    if not path.is_absolute() or ".." in path.parts:
        raise _Unknown
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for name in path.parts[1:]:
            child = os.open(name, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid() or not stat.S_ISDIR(info.st_mode):
            raise _Unknown
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_rollout(home: Path, session_id: str, budget: _Budget):
    date = _thread_date(session_id)
    home_fd = _safe_directory(home)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    matches = []
    count = 0
    try:
        for offset in (-1, 0, 1):
            budget.check()
            day = date + dt.timedelta(days=offset)
            directory = os.dup(home_fd)
            try:
                for name in ("sessions", f"{day.year:04}", f"{day.month:02}", f"{day.day:02}"):
                    child = os.open(name, flags, dir_fd=directory)
                    os.close(directory)
                    directory = child
                    if os.fstat(directory).st_uid != os.getuid():
                        raise _Unknown
                pattern = re.compile(r"rollout-" + day.isoformat() + r"T(?:[01][0-9]|2[0-3])-[0-5][0-9]-[0-5][0-9]-"
                                     + re.escape(session_id) + r"\.jsonl")
                with os.scandir(directory) as entries:
                    for entry in entries:
                        count += 1
                        budget.check()
                        if count > MAX_DIRECTORY_ENTRIES:
                            raise _Unknown
                        if pattern.fullmatch(entry.name):
                            descriptor = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                                 dir_fd=directory)
                            info = os.fstat(descriptor)
                            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                                os.close(descriptor)
                                raise _Unknown
                            matches.append(descriptor)
            except FileNotFoundError:
                pass
            finally:
                os.close(directory)
        if len(matches) != 1:
            raise _Unknown
        descriptor = matches.pop()
        return descriptor
    finally:
        os.close(home_fd)
        for descriptor in matches:
            os.close(descriptor)


def _boundary(descriptor, size):
    tail = os.pread(descriptor, min(size, BOUNDARY_BYTES), max(0, size - BOUNDARY_BYTES))
    if len(tail) != min(size, BOUNDARY_BYTES) or (size and tail[-1:] != b"\n"):
        raise _Unknown
    return hashlib.sha256(tail).hexdigest()


def prepare_codex_usage(home: Path, session_id: str | None, cwd: Path, *,
                        deadline: float | None = None) -> dict | None:
    """Snapshot a known resumed rollout; home is the effective CODEX_HOME."""
    try:
        budget = _Budget(deadline)
        home, cwd = Path(home), Path(cwd)
        if not cwd.is_absolute() or ".." in cwd.parts:
            return None
        directory = _safe_directory(home)
        try:
            info = os.fstat(directory)
            home_identity = [info.st_dev, info.st_ino]
        finally:
            os.close(directory)
        run = {"version": 1, "home": str(home), "home_identity": home_identity,
               "session_id": session_id, "cwd": str(cwd), "prepared_at": time.time(), "boundary": None}
        if session_id is not None:
            descriptor = _open_rollout(home, session_id, budget)
            try:
                info = os.fstat(descriptor)
                if info.st_size == 0:
                    raise _Unknown
                run["boundary"] = {"dev": info.st_dev, "ino": info.st_ino, "size": info.st_size,
                                   "digest": _boundary(descriptor, info.st_size)}
            finally:
                os.close(descriptor)
        budget.check()
        return run
    except (OSError, ValueError, TypeError, OverflowError, _Unknown):
        return None


def _stamp(value):
    if not isinstance(value, str):
        raise _Unknown
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise _Unknown
    return parsed.timestamp()


def _fresh(value, started, finished):
    return started - 1 <= value <= finished + 1


def _native_projection(record):
    top = record.object()
    kind = record.scalar(top, "type")
    if kind not in ("session_meta", "turn_context", "event_msg"):
        return None
    payload = record.object(top.get("payload", (-1, -1)))
    row = {"kind": kind, "timestamp": record.scalar(top, "timestamp")}
    if kind == "event_msg":
        row["type"] = record.scalar(payload, "type")
        if row["type"] not in ("task_started", "task_complete"):
            return None
        for key in ("turn_id",):
            row[key] = record.scalar(payload, key)
        for key in ("started_at", "completed_at"):
            row[key] = record.scalar(payload, key, int)
        if row["type"] == "task_complete" and "error" in payload:
            error = record.object(payload["error"])
            row["error"] = {key: record.scalar(error, key) for key in ("message", "codex_error_info")}
    elif kind == "session_meta":
        for key in ("id", "timestamp", "cwd"):
            row[key] = record.scalar(payload, key)
    else:
        for key in ("turn_id", "cwd", "model", "effort"):
            row[key] = record.scalar(payload, key)
    return row


def _codex_terminal(stdout, budget):
    thread = None
    started = 0
    terminal = None
    thread_seen = terminal_seen = False
    for record in _records(stdout.encode("utf-8", errors="strict"), budget):
        top = record.object()
        kind = record.scalar(top, "type")
        if terminal_seen:
            raise _Unknown
        if kind == "thread.started":
            if thread_seen or started:
                raise _Unknown
            thread_seen = True
            thread = record.scalar(top, "thread_id")
            if not thread:
                raise _Unknown
        elif kind == "turn.started":
            if not thread or started:
                raise _Unknown
            started += 1
        elif kind in ("turn.completed", "turn.failed"):
            terminal_seen = True
            if kind != "turn.failed" or started != 1:
                raise _Unknown
            error = record.object(top.get("error", (-1, -1)))
            terminal = record.scalar(error, "message")
            if not terminal:
                raise _Unknown
        elif kind not in ("item.started", "item.updated", "item.completed", "error"):
            raise _Unknown
    if thread is None or started != 1 or not _usage_message(terminal):
        raise _Unknown
    _thread_date(thread)
    return thread, terminal


def _codex(stdout, run, started, finished, budget, model, effort):
    thread, message = _codex_terminal(stdout, budget)
    if (not isinstance(run, dict) or type(run.get("version")) is not int or run["version"] != 1
            or run.get("session_id") not in (None, thread)):
        raise _Unknown
    if run.get("session_id") is None and not _fresh((uuid.UUID(thread).int >> 80) / 1000, started, finished):
        raise _Unknown
    if not _fresh(run["prepared_at"], started, finished):
        raise _Unknown
    home = Path(run["home"])
    directory = _safe_directory(home)
    try:
        info = os.fstat(directory)
        if run["home_identity"] != [info.st_dev, info.st_ino]:
            raise _Unknown
    finally:
        os.close(directory)
    descriptor = _open_rollout(home, thread, budget)
    try:
        info = os.fstat(descriptor)
        boundary = run.get("boundary")
        offset = 0
        if run.get("session_id") is not None:
            if not isinstance(boundary, dict) or (info.st_dev, info.st_ino) != (boundary["dev"], boundary["ino"]):
                raise _Unknown
            offset = boundary["size"]
            if type(offset) is not int or offset < 0 or info.st_size < offset:
                raise _Unknown
            if _boundary(descriptor, offset) != boundary["digest"]:
                raise _Unknown
        elif boundary is not None:
            raise _Unknown
        if info.st_size - offset > MAX_SCAN_BYTES:
            raise _Unknown
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            first = stream.readline(MAX_RECORD_BYTES + 1)
            if len(first) > MAX_RECORD_BYTES or not first.endswith(b"\n"):
                raise _Unknown
            meta = _native_projection(_JSON(first, budget))
            if not meta or meta["kind"] != "session_meta" or meta["id"] != thread:
                raise _Unknown
            if not offset and not _fresh(_stamp(meta["timestamp"]), started, finished):
                raise _Unknown
            if offset:
                stream.seek(offset)
            remaining = MAX_SCAN_BYTES - len(first)
            if remaining < 0:
                raise _Unknown
            raw = stream.read(remaining + 1)
            if len(raw) > remaining:
                raise _Unknown
        if os.fstat(descriptor).st_size != info.st_size:
            raise _Unknown
        rows = []
        for record in _records(raw, budget, require_lf=True, initial_count=1):
            row = _native_projection(record)
            if row is None:
                continue
            if row["kind"] == "session_meta":
                raise _Unknown
            if not _fresh(_stamp(row["timestamp"]), started, finished):
                raise _Unknown
            rows.append(row)
        if len(rows) != 3:
            raise _Unknown
        beginning, context, terminal = rows
        if (beginning.get("type") != "task_started" or context["kind"] != "turn_context"
                or terminal.get("type") != "task_complete"):
            raise _Unknown
        turn = beginning.get("turn_id")
        if not turn or context.get("turn_id") != turn or terminal.get("turn_id") != turn:
            raise _Unknown
        if (context.get("cwd") != run["cwd"] or context.get("model") != model
                or context.get("effort") != effort):
            raise _Unknown
        start_time, end_time = beginning.get("started_at"), terminal.get("completed_at")
        if (type(start_time) is not int or type(end_time) is not int
                or terminal.get("started_at") != start_time or end_time < start_time
                or not _fresh(start_time, started, finished) or not _fresh(end_time, started, finished)):
            raise _Unknown
        error = terminal.get("error", {})
        if error.get("codex_error_info") != "usage_limit_exceeded" or error.get("message") != message:
            raise _Unknown
        budget.check()
        return {"code": "usage_limit_exceeded", "evidence": "codex_exec_and_current_rollout",
                "message": message}
    finally:
        os.close(descriptor)


def _claude(stdout, budget):
    terminal = None
    sessions = set()
    for record in _records(stdout.encode("utf-8", errors="strict"), budget):
        top = record.object()
        kind = record.scalar(top, "type")
        if terminal is not None:
            raise _Unknown
        if kind not in ("system", "assistant", "user", "result", "stream_event", "rate_limit_event",
                        "tool_progress", "tool_use_summary", "auth_status"):
            raise _Unknown
        session = record.scalar(top, "session_id")
        if session is not None:
            sessions.add(session)
        if kind == "result":
            terminal = {key: record.scalar(top, key) for key in
                        ("subtype", "api_error", "api_error_origin", "session_id")}
            terminal["is_error"] = record.scalar(top, "is_error", bool)
    if (not terminal or terminal.get("is_error") is not True
            or terminal.get("subtype") not in ("success", "error_during_execution")
            or not terminal.get("session_id") or sessions != {terminal["session_id"]}
            or terminal.get("api_error") != "usage_limit_reached"
            or terminal.get("api_error_origin") != "first_party"):
        raise _Unknown
    budget.check()
    return {"code": "usage_limit_reached", "evidence": "claude_first_party_terminal",
            "message": "Claude reported its first-party usage limit was reached."}


def detect_usage(provider: str, stdout: str, returncode: int, *, model: str, effort: str = "max",
                 codex_run: dict | None = None, started_at: float | None = None,
                 finished_at: float | None = None, deadline: float | None = None) -> dict | None:
    """Verify terminal usage evidence against the caller's trusted profile."""
    try:
        # Windows crash statuses can be positive; its normal-exit proof is unsupported.
        if os.name != "posix":
            return None
        budget = _Budget(deadline)
        if (not isinstance(provider, str) or provider not in MODELS
                or not isinstance(model, str) or _MODEL_SELECTOR.fullmatch(model) is None
                or not isinstance(effort, str) or effort not in EFFORTS
                or type(returncode) is not int or not 0 <= returncode <= 255
                or not isinstance(stdout, str)):
            return None
        if provider == "claude":
            if _CLAUDE_MODEL.fullmatch(model) is None:
                return None
            return _claude(stdout, budget)
        if (type(started_at) not in (int, float) or type(finished_at) not in (int, float)
                or not math.isfinite(started_at) or not math.isfinite(finished_at) or finished_at < started_at):
            return None
        return _codex(stdout, codex_run, started_at, finished_at, budget, model, effort)
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError, _Unknown):
        return None
