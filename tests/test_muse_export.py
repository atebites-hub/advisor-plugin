"""A native Muse export contains only relocatable runtime and skill files."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/export_muse.py"
SPEC = importlib.util.spec_from_file_location("advisor_muse_export", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)

FILES = (
    "advisor.py", "advisor.py.lock", "configuration.py", "session_context.py",
    "review_checkpoints.py", "usage_limits.py", "skills/advisor/SKILL.md",
    "skills/advisor-setup/SKILL.md",
)


class MuseExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.source = self.repository / "plugins/advisor"
        self.source.mkdir(parents=True)
        self.metadata = {"name": "advisor", "version": "9.8.7", "description": "Fixture description."}
        (self.source / "plugin.json").write_text(json.dumps(self.metadata))
        for relative in FILES:
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((relative + "\r\nfixture\n").encode())
        setting = patch.object(exporter, "REPOSITORY_ROOT", self.repository)
        setting.start()
        self.addCleanup(setting.stop)
        self.destination = self.root / "new bundle"

    def test_exports_exact_files_native_schema_and_unchanged_bytes(self):
        for relative in (".git/config", ".claude-plugin/plugin.json", "mcp.json", ".mcp.json",
                         "config.json", "auth.json", "sessions/private.json", "cache/private"):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("private material must not be exported")
        result = exporter.export_muse(self.destination)
        self.assertEqual(result, self.destination)
        paths = {str(path.relative_to(result)) for path in result.rglob("*") if path.is_file()}
        self.assertEqual(paths, set(FILES) | {".muse-plugin/plugin.json"})
        for relative in FILES:
            self.assertEqual((result / relative).read_bytes(), (self.source / relative).read_bytes())
        manifest = json.loads((result / ".muse-plugin/plugin.json").read_text())
        self.assertEqual(manifest, {
            "schemaVersion": 1, "name": "advisor", "displayName": "Advisor",
            "version": self.metadata["version"], "description": self.metadata["description"],
            "compat": {"source": "native", "manifestDir": ".muse-plugin"},
            "capabilities": {
                "skills": [{"id": name, "path": f"skills/{name}/SKILL.md", "enabledDefault": True}
                           for name in ("advisor", "advisor-setup")],
                "hooks": [{"id": "session-start", "event": "SessionStart",
                           "command": ["uv", "run", "--script", "./advisor.py", "session-start"],
                           "timeoutMs": 10000}],
                "mcpServers": [{"id": "advisor", "transport": "stdio",
                                "command": ["uv", "run", "--script", "./advisor.py", "serve"]}],
            },
        })
        self.assertNotIn(str(self.repository), json.dumps(manifest))

    def test_existing_files_directories_and_symlinks_are_never_replaced(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"keep")
        for kind in ("file", "directory", "symlink", "dangling-symlink"):
            destination = self.root / kind
            if kind == "file":
                destination.write_bytes(b"original")
            elif kind == "directory":
                destination.mkdir()
                (destination / "keep").write_bytes(b"original")
            else:
                destination.symlink_to(sentinel if kind == "symlink" else self.root / "missing")
            before = destination.lstat()
            with self.subTest(kind=kind), self.assertRaises((ValueError, FileExistsError)):
                exporter.export_muse(destination)
            self.assertEqual(destination.lstat(), before)
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_requires_absolute_destination_and_existing_directory_parent(self):
        for destination in (Path("relative"), self.root / "missing/child", self.source / "advisor.py/child"):
            with self.subTest(destination=destination), self.assertRaises((ValueError, OSError)):
                exporter.export_muse(destination)
        self.assertFalse(self.destination.exists())

    def test_rejects_repository_overlap_including_parent_alias(self):
        alias = self.root / "repository-alias"
        alias.symlink_to(self.repository, target_is_directory=True)
        for destination in (self.repository, self.repository / "new", self.source / "new", self.root,
                            alias / "new"):
            with self.subTest(destination=destination), self.assertRaises((ValueError, FileExistsError)):
                exporter.export_muse(destination)
        self.assertFalse((self.repository / "new").exists())
        self.assertFalse((self.source / "new").exists())

    def test_preflights_missing_or_nonregular_sources_before_creating_destination(self):
        for relative in ("advisor.py", "skills/advisor-setup/SKILL.md", "plugin.json"):
            source = self.source / relative
            original = source.read_bytes()
            source.unlink()
            with self.subTest(relative=relative), self.assertRaises((ValueError, OSError)):
                exporter.export_muse(self.destination)
            self.assertFalse(self.destination.exists())
            source.mkdir()
            with self.assertRaises((ValueError, OSError)):
                exporter.export_muse(self.destination)
            self.assertFalse(self.destination.exists())
            source.rmdir()
            source.write_bytes(original)

    def test_rejects_symlink_source_files_and_directories(self):
        source = self.source / "advisor.py"
        source.rename(self.root / "outside.py")
        source.symlink_to(self.root / "outside.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            exporter.export_muse(self.destination)
        self.assertFalse(self.destination.exists())
        source.unlink()
        source.write_text("restored")
        skills = self.source / "skills"
        skills.rename(self.root / "outside-skills")
        skills.symlink_to(self.root / "outside-skills", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            exporter.export_muse(self.destination)
        self.assertFalse(self.destination.exists())

    def test_rejects_invalid_shared_metadata_before_creating_destination(self):
        for value in (b"{broken", b"[]", b"\xff", b'{}', b'{"version":false,"description":"text"}',
                      b'{"version":"1","description":" "}'):
            (self.source / "plugin.json").write_bytes(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                exporter.export_muse(self.destination)
            self.assertFalse(self.destination.exists())

    def test_exclusive_directory_reservation_preserves_a_race_created_destination(self):
        original = Path.mkdir

        def create_first(path, *args, **kwargs):
            if path == self.destination:
                original(path)
                (path / "keep").write_text("created by another writer")
            return original(path, *args, **kwargs)

        with patch.object(Path, "mkdir", create_first), self.assertRaises(FileExistsError):
            exporter.export_muse(self.destination)
        self.assertEqual(list(self.destination.iterdir()), [self.destination / "keep"])
        self.assertEqual((self.destination / "keep").read_text(), "created by another writer")

    def test_write_failure_leaves_owned_partial_output_without_native_manifest(self):
        sentinel = self.root / "untouched"
        sentinel.write_bytes(b"keep")
        original = Path.open

        def fail_write(path, mode="r", *args, **kwargs):
            if path == self.destination / "configuration.py" and mode == "xb":
                raise OSError("injected write failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_write), self.assertRaisesRegex(OSError, "injected"):
            exporter.export_muse(self.destination)
        self.assertEqual((self.destination / "advisor.py").read_bytes(), (self.source / "advisor.py").read_bytes())
        self.assertFalse((self.destination / ".muse-plugin/plugin.json").exists())
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_native_manifest_is_written_last_and_cli_reports_partial_failure(self):
        original = Path.open

        def fail_manifest(path, mode="r", *args, **kwargs):
            if path == self.destination / ".muse-plugin/plugin.json" and mode == "xb":
                raise OSError("injected manifest failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_manifest), patch.object(sys, "argv", [str(SCRIPT), str(self.destination)]), \
                contextlib.redirect_stderr(io.StringIO()) as output:
            result = exporter.main()
        self.assertEqual(result, 1)
        self.assertIn("partial", output.getvalue())
        self.assertIn("injected manifest failure", output.getvalue())
        self.assertTrue(all((self.destination / relative).is_file() for relative in FILES))
        self.assertFalse((self.destination / ".muse-plugin/plugin.json").exists())

    def test_real_cli_bundle_runs_doctor_after_relocation_outside_checkout(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), str(self.destination)], cwd=self.root,
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        relocated = self.root / "relocated bundle"
        self.destination.rename(relocated)
        original_files = {str(path.relative_to(relocated)): path.read_bytes()
                          for path in relocated.rglob("*") if path.is_file()}
        config = self.root / "advisor-settings.json"
        config.write_text(json.dumps({"advisors": {"claude": {"enabled": False},
                                                  "codex": {"model": "gpt-6.1-sol", "effort": "max"}}}))
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ADVISOR_")}
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        completed = subprocess.run([sys.executable, str(relocated / "advisor.py"), "doctor", "--config", str(config)],
                                   cwd=self.root, env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        profiles = json.loads(completed.stdout)["advisors"]
        self.assertFalse(profiles["claude"]["enabled"])
        self.assertEqual((profiles["codex"]["model"], profiles["codex"]["effort"]), ("gpt-6.1-sol", "max"))
        self.assertEqual({str(path.relative_to(relocated)): path.read_bytes()
                          for path in relocated.rglob("*") if path.is_file()}, original_files)
        started = subprocess.run([sys.executable, str(relocated / "advisor.py"), "session-start"],
                                 cwd=self.root, env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("additionalContext", json.loads(started.stdout)["hookSpecificOutput"])
        self.assertEqual({str(path.relative_to(relocated)): path.read_bytes()
                          for path in relocated.rglob("*") if path.is_file()}, original_files)


if __name__ == "__main__":
    unittest.main()
