import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "plugins/advisor/session_context.py"
SPEC = importlib.util.spec_from_file_location("advisor_file_context_tests", PATH)
context = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context
SPEC.loader.exec_module(context)


class FileSnapshotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.state = self.root / "new-state/nested"
        self.request = {"workspace": str(self.workspace), "host": "claude",
                        "session_id": "session-fixture", "task_id": "task-fixture",
                        "context_files": ["source.py"]}
        self.source = self.workspace / "source.py"
        self.source.write_bytes(b"value = 1\r\n")

    def capture(self, request=None, redact=lambda value: value):
        return context.capture_file_context(request or self.request, self.state, redact)

    def load(self, snapshot_id, request=None):
        return context.load_file_context(snapshot_id, request or self.request, self.state)

    def snapshot_path(self, snapshot_id):
        return self.state / "file-contexts" / f"{snapshot_id}.json"

    def forged(self, payload):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        snapshot_id = hashlib.sha256(encoded).hexdigest()
        path = self.snapshot_path(snapshot_id)
        path.write_bytes(encoded)
        path.chmod(0o600)
        return snapshot_id

    def test_literal_unicode_crlf_sorted_paths_and_redaction_before_storage(self):
        text = 'name = "雪🚗"\r\nsecret = "test-secret"\r\n'
        self.source.write_bytes(text.encode("utf-8"))
        (self.workspace / "nested").mkdir()
        (self.workspace / "nested/other.txt").write_bytes(b"untouched\n")
        self.request["context_files"] = ["source.py", "nested/other.txt"]
        snapshot_id = self.capture(redact=lambda value: value.replace("test-secret", "[REDACTED]"))
        self.assertRegex(snapshot_id, r"^[a-f0-9]{64}$")
        raw = self.snapshot_path(snapshot_id).read_bytes()
        self.assertNotIn(b"test-secret", raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), snapshot_id)
        payload = self.load(snapshot_id)
        self.assertEqual(payload["binding"], {key: self.request[key]
                         for key in ("workspace", "host", "session_id", "task_id")})
        self.assertEqual([entry["path"] for entry in payload["files"]],
                         ["nested/other.txt", "source.py"])
        entry = payload["files"][1]
        expected = text.replace("test-secret", "[REDACTED]")
        self.assertEqual(entry["content"], expected)
        self.assertEqual(entry["bytes"], len(expected.encode("utf-8")))
        self.assertEqual(entry["sha256"], hashlib.sha256(expected.encode("utf-8")).hexdigest())
        self.assertTrue(entry["redacted"])
        self.assertFalse(payload["files"][0]["redacted"])

    def test_snapshot_is_frozen_and_repeated_capture_never_replaces_it(self):
        snapshot_id = self.capture()
        path = self.snapshot_path(snapshot_id)
        before = path.stat()
        self.assertEqual(self.capture(), snapshot_id)
        self.assertEqual(path.stat().st_ino, before.st_ino)
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.source.write_bytes(b"changed source\n")
        self.assertEqual(self.load(snapshot_id)["files"][0]["content"], "value = 1\r\n")
        self.assertNotEqual(self.capture(), snapshot_id)

    def test_storage_and_snapshot_are_private_in_new_state_directories(self):
        snapshot_id = self.capture()
        for path in (self.state.parent, self.state, self.state / "file-contexts"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.snapshot_path(snapshot_id).stat().st_mode), 0o600)

    def test_invalid_selections_are_rejected_without_creating_state(self):
        invalid = (None, "source.py", [], ["source.py"] * 2, [1], [None],
                   ["/etc/passwd"], ["../source.py"], ["nested/../source.py"],
                   ["./source.py"], ["nested//source.py"], ["source.py/"],
                   [""], ["source.py\0"], ["nested\\source.py"],
                   [f"file-{number}" for number in range(33)])
        for selection in invalid:
            with self.subTest(selection=selection), self.assertRaises(context.ContextCaptureError):
                self.capture(self.request | {"context_files": selection})
        self.assertFalse(self.state.exists())

    def test_glob_characters_are_literal_and_never_expand(self):
        self.request["context_files"] = ["*.py"]
        with self.assertRaises(context.ContextCaptureError):
            self.capture()
        (self.workspace / "*.py").write_bytes(b"literal wildcard filename\n")
        self.assertEqual(self.load(self.capture())["files"][0]["path"], "*.py")

    def test_missing_scope_and_non_absolute_workspace_are_rejected(self):
        for key in ("workspace", "host", "session_id", "task_id"):
            for value in (None, "", " ", 1, "bad\0value"):
                with self.subTest(key=key, value=value), self.assertRaises(context.ContextCaptureError):
                    self.capture(self.request | {key: value})
        with self.assertRaises(context.ContextCaptureError):
            self.capture(self.request | {"workspace": "relative/workspace"})

    def test_invalid_utf8_nul_and_invalid_redactor_output_fail_before_storage(self):
        for raw in (b"\xff", b"valid\0binary"):
            self.source.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(context.ContextCaptureError):
                self.capture()
        self.source.write_bytes(b"valid")
        for output in (None, 3, "nul\0output", "unpaired\ud800"):
            with self.subTest(output=repr(output)), self.assertRaises(context.ContextCaptureError):
                self.capture(redact=lambda value: output)
        self.assertFalse(self.state.exists())

    def test_raw_limit_is_aggregate_actual_bytes_and_accepts_exact_boundary(self):
        self.source.write_bytes(b"1234")
        (self.workspace / "second.txt").write_bytes(b"567")
        self.request["context_files"] = ["source.py", "second.txt"]
        with patch.object(context, "MAX_FILE_SOURCE_BYTES", 6):
            with self.assertRaises(context.ContextCaptureError):
                self.capture()
        self.assertFalse(self.state.exists())
        with patch.object(context, "MAX_FILE_SOURCE_BYTES", 7):
            self.assertEqual(len(self.load(self.capture())["files"]), 2)

    def test_serialized_limit_is_independent_and_includes_redaction_expansion(self):
        with patch.object(context, "MAX_FILE_CONTEXT_BYTES", 100):
            with self.assertRaisesRegex(context.ContextCaptureError, "serialized"):
                self.capture()
        self.assertFalse(self.state.exists())
        with patch.object(context, "MAX_FILE_SOURCE_BYTES", 100), \
                patch.object(context, "MAX_FILE_CONTEXT_BYTES", 1000):
            with self.assertRaisesRegex(context.ContextCaptureError, "serialized"):
                self.capture(redact=lambda value: "x" * 1000)
        self.assertFalse(self.state.exists())

    def test_leaf_parent_and_workspace_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_bytes(b"outside secret")
        (self.workspace / "leaf").symlink_to(outside / "secret.txt")
        (self.workspace / "parent").symlink_to(outside, target_is_directory=True)
        for selected in ("leaf", "parent/secret.txt"):
            with self.subTest(selected=selected), self.assertRaises(context.ContextCaptureError):
                self.capture(self.request | {"context_files": [selected]})
        alias = self.root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaises(context.ContextCaptureError):
            self.capture(self.request | {"workspace": str(alias)})
        self.assertFalse(self.state.exists())

    def test_directory_and_fifo_are_rejected_without_a_blocking_open(self):
        (self.workspace / "directory").mkdir()
        with self.assertRaises(context.ContextCaptureError):
            self.capture(self.request | {"context_files": ["directory"]})
        os.mkfifo(self.workspace / "pipe")
        real_open = os.open

        def checked_open(name, flags, *args, **kwargs):
            if name == "pipe":
                self.assertTrue(flags & os.O_NONBLOCK, "FIFO must never be opened in blocking mode")
            return real_open(name, flags, *args, **kwargs)

        with patch.object(context.os, "open", side_effect=checked_open) as opened:
            with patch.object(context.os, "supports_dir_fd", os.supports_dir_fd | {opened}):
                with self.assertRaises(context.ContextCaptureError):
                    self.capture(self.request | {"context_files": ["pipe"]})

    def test_detectable_mutation_during_read_is_rejected(self):
        real_read = os.read
        changed = False

        def read_and_change(descriptor, count):
            nonlocal changed
            if not changed:
                changed = True
                self.source.write_bytes(b"different size\n")
            return real_read(descriptor, count)

        with patch.object(context.os, "read", side_effect=read_and_change):
            with self.assertRaisesRegex(context.ContextCaptureError, "changed"):
                self.capture()
        self.assertFalse(self.state.exists())

    def test_path_replacement_during_read_is_rejected(self):
        real_read = os.read
        replaced = False

        def read_and_replace(descriptor, count):
            nonlocal replaced
            if not replaced:
                replaced = True
                replacement = self.workspace / "replacement"
                replacement.write_bytes(self.source.read_bytes())
                replacement.replace(self.source)
            return real_read(descriptor, count)

        with patch.object(context.os, "read", side_effect=read_and_replace):
            with self.assertRaisesRegex(context.ContextCaptureError, "changed"):
                self.capture()

    def test_timestamp_only_change_during_read_is_rejected(self):
        real_read = os.read
        before = self.source.stat()
        changed = False

        def read_and_touch(descriptor, count):
            nonlocal changed
            result = real_read(descriptor, count)
            if not changed:
                changed = True
                os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
            return result

        with patch.object(context.os, "read", side_effect=read_and_touch):
            with self.assertRaisesRegex(context.ContextCaptureError, "changed"):
                self.capture()

    def test_parent_directory_replacement_during_read_is_rejected(self):
        parent = self.workspace / "nested"
        parent.mkdir()
        self.source.replace(parent / "source.py")
        self.request["context_files"] = ["nested/source.py"]
        real_read = os.read
        changed = False

        def read_and_move(descriptor, count):
            nonlocal changed
            if not changed:
                changed = True
                parent.rename(self.workspace / "old-nested")
                parent.mkdir()
            return real_read(descriptor, count)

        with patch.object(context.os, "read", side_effect=read_and_move):
            with self.assertRaisesRegex(context.ContextCaptureError, "directory changed"):
                self.capture()

    def test_workspace_replacement_during_read_is_rejected(self):
        real_read = os.read
        changed = False

        def read_and_move(descriptor, count):
            nonlocal changed
            if not changed:
                changed = True
                self.workspace.rename(self.root / "old-workspace")
                self.workspace.mkdir()
            return real_read(descriptor, count)

        with patch.object(context.os, "read", side_effect=read_and_move):
            with self.assertRaisesRegex(context.ContextCaptureError, "workspace changed"):
                self.capture()

    def test_scope_is_bound_to_workspace_host_session_and_task(self):
        snapshot_id = self.capture()
        other = self.root / "other-workspace"
        other.mkdir()
        for key, value in (("workspace", str(other)), ("host", "cursor"),
                           ("session_id", "another-session"), ("task_id", "another-task")):
            with self.subTest(key=key), self.assertRaises(context.ContextCaptureError):
                self.load(snapshot_id, self.request | {key: value})

    def test_invalid_identifiers_and_tampered_bytes_are_rejected(self):
        snapshot_id = self.capture()
        for value in ("../snapshot", snapshot_id.upper(), "0" * 63, None, 3):
            with self.subTest(value=value), self.assertRaises(context.ContextCaptureError):
                self.load(value)
        self.snapshot_path(snapshot_id).write_bytes(b"{}")
        with self.assertRaisesRegex(context.ContextCaptureError, "integrity"):
            self.load(snapshot_id)

    def test_rehashed_bad_version_and_content_metadata_are_rejected(self):
        payload = self.load(self.capture())
        altered_payloads = []
        for version in (2, True, "1"):
            altered_payloads.append(payload | {"schema_version": version})
        altered_payloads.append(payload | {"files": []})
        altered_payloads.append(payload | {"unexpected": "field"})
        for key, value in (("sha256", "0" * 64), ("bytes", True), ("bytes", 0),
                           ("redacted", 1), ("content", "\0"), ("path", "../escape")):
            altered = copy.deepcopy(payload)
            altered["files"][0][key] = value
            altered_payloads.append(altered)
        for altered in altered_payloads:
            with self.subTest(payload=altered), self.assertRaises(context.ContextCaptureError):
                self.load(self.forged(altered))

    def test_existing_tampered_snapshot_is_never_overwritten(self):
        snapshot_id = self.capture()
        path = self.snapshot_path(snapshot_id)
        path.write_bytes(b"corrupt snapshot")
        with self.assertRaisesRegex(context.ContextCaptureError, "integrity"):
            self.capture()
        self.assertEqual(path.read_bytes(), b"corrupt snapshot")
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_temporary_name_collision_does_not_remove_an_existing_file(self):
        snapshot_id = self.capture()
        collision = self.snapshot_path(snapshot_id).parent / f".{snapshot_id}.{'00' * 16}.tmp"
        collision.write_bytes(b"existing temporary file")
        with patch.object(context.os, "urandom", return_value=b"\0" * 16):
            with self.assertRaises(context.ContextCaptureError):
                self.capture()
        self.assertEqual(collision.read_bytes(), b"existing temporary file")
        self.assertEqual(self.load(snapshot_id)["files"][0]["content"], "value = 1\r\n")

    def test_symlinked_state_storage_or_snapshot_is_rejected(self):
        outside = self.root / "outside-storage"
        outside.mkdir()
        self.state.parent.mkdir(parents=True)
        self.state.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(context.ContextCaptureError):
            self.capture()
        self.state.unlink()
        self.state.mkdir()
        (self.state / "file-contexts").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(context.ContextCaptureError):
            self.capture()
        (self.state / "file-contexts").unlink()
        snapshot_id = self.capture()
        path = self.snapshot_path(snapshot_id)
        target = outside / "snapshot.json"
        path.replace(target)
        path.symlink_to(target)
        with self.assertRaises(context.ContextCaptureError):
            self.load(snapshot_id)

    def test_world_readable_snapshot_or_storage_is_rejected_on_load(self):
        snapshot_id = self.capture()
        path = self.snapshot_path(snapshot_id)
        path.chmod(0o644)
        with self.assertRaises(context.ContextCaptureError):
            self.load(snapshot_id)
        path.chmod(0o600)
        path.parent.chmod(0o755)
        with self.assertRaises(context.ContextCaptureError):
            self.load(snapshot_id)

    def test_missing_secure_primitives_fail_closed_without_creating_state(self):
        with patch.object(context.os, "supports_dir_fd", set()):
            with self.assertRaisesRegex(context.ContextCaptureError, "unsupported"):
                self.capture()
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
