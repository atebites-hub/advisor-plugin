"""The native Antigravity bundle uses the shared safe public-file export."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import export_antigravity as exporter


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/export_antigravity.py"
FILES = (
    "advisor.py", "advisor.py.lock", "configuration.py", "session_context.py",
    "review_checkpoints.py", "usage_limits.py", "skills/advisor/SKILL.md",
    "skills/advisor-setup/SKILL.md",
)


class AntigravityExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.source = self.repository / "plugins/advisor"
        self.source.mkdir(parents=True)
        (self.source / "plugin.json").write_text(json.dumps({
            "name": "advisor", "version": "9.8.7", "description": "Fixture description.",
        }))
        for relative in FILES:
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((relative + "\r\nfixture\n").encode())
        setting = patch.object(exporter, "REPOSITORY_ROOT", self.repository)
        setting.start()
        self.addCleanup(setting.stop)
        self.destination = self.root / "new bundle"

    def test_exports_exact_public_inventory_and_native_launch_contract(self):
        for relative in ("auth.json", ".claude-plugin/plugin.json", "sessions/private.json", "mcp.json"):
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("private material must not be exported")
        result = exporter.export_antigravity(self.destination)
        self.assertEqual(result, self.destination)
        inventory = {str(path.relative_to(result)) for path in result.rglob("*") if path.is_file()}
        self.assertEqual(inventory, set(FILES) | {"plugin.json", "mcp_config.json", "hooks.json"})
        for relative in FILES:
            self.assertEqual((result / relative).read_bytes(), (self.source / relative).read_bytes())
        self.assertEqual(json.loads((result / "plugin.json").read_text()), {
            "name": "advisor", "description": "Fixture description.",
        })
        self.assertEqual(json.loads((result / "mcp_config.json").read_text()), {
            "mcpServers": {"advisor": {"command": "uv", "args": ["run", "--script", "./advisor.py", "serve"]}},
        })
        self.assertEqual(json.loads((result / "hooks.json").read_text()), {
            "advisor": {"SessionStart": [{"type": "command", "command":
                "uv run --script ./advisor.py session-start --hook-format antigravity", "timeout": 10}]},
        })

    def test_reuses_destination_and_source_safety_before_creating_output(self):
        alias = self.root / "alias"
        alias.symlink_to(self.repository, target_is_directory=True)
        for destination in (Path("relative"), self.root / "missing/child", self.repository / "new",
                            alias / "new", self.root):
            with self.subTest(destination=destination), self.assertRaises((ValueError, OSError)):
                exporter.export_antigravity(destination)
        source = self.source / "advisor.py"
        source.rename(self.root / "outside.py")
        source.symlink_to(self.root / "outside.py")
        with self.assertRaisesRegex(ValueError, "symlink"):
            exporter.export_antigravity(self.destination)
        self.assertFalse(self.destination.exists())

    def test_existing_destination_is_never_replaced(self):
        self.destination.mkdir()
        sentinel = self.destination / "keep"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            exporter.export_antigravity(self.destination)
        self.assertEqual(list(self.destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_failure_before_native_marker_leaves_partial_output_and_reports_error(self):
        original = Path.open

        def fail_hook(path, mode="r", *args, **kwargs):
            if path == self.destination / "hooks.json" and mode == "xb":
                raise OSError("injected hook write failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_hook), \
                patch.object(sys, "argv", [str(SCRIPT), str(self.destination)]), \
                contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(exporter.main(), 1)
        self.assertIn("partial", output.getvalue())
        self.assertTrue(all((self.destination / relative).is_file() for relative in FILES))
        self.assertTrue((self.destination / "mcp_config.json").is_file())
        self.assertFalse((self.destination / "plugin.json").exists())

    def test_native_marker_is_last(self):
        original = Path.open

        def fail_manifest(path, mode="r", *args, **kwargs):
            if path == self.destination / "plugin.json" and mode == "xb":
                self.assertTrue((self.destination / "hooks.json").is_file())
                self.assertTrue((self.destination / "mcp_config.json").is_file())
                raise OSError("injected manifest write failure")
            return original(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_manifest), self.assertRaisesRegex(OSError, "manifest"):
            exporter.export_antigravity(self.destination)
        self.assertFalse((self.destination / "plugin.json").exists())

    def test_real_cli_relocates_without_mutating_bundle_and_injects_native_policy(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), str(self.destination)], cwd=self.root,
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        relocated = self.root / "relocated bundle"
        self.destination.rename(relocated)
        original_files = {str(path.relative_to(relocated)): path.read_bytes()
                          for path in relocated.rglob("*") if path.is_file()}
        environment = {key: value for key, value in os.environ.items() if not key.startswith("ADVISOR_")}
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        environment.pop("PYTHONPYCACHEPREFIX", None)
        completed = subprocess.run([sys.executable, str(relocated / "advisor.py"), "session-start",
                                    "--hook-format", "antigravity"], cwd=relocated, env=environment,
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Advisor SessionStart instructions", json.loads(completed.stdout)
                      ["injectSteps"][0]["systemMessage"]["systemMessage"])
        self.assertEqual({str(path.relative_to(relocated)): path.read_bytes()
                          for path in relocated.rglob("*") if path.is_file()}, original_files)


if __name__ == "__main__":
    unittest.main()
