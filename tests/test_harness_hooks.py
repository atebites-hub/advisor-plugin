"""Each host loads only its own startup-hook file and output schema."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "plugins/advisor"
sys.path.insert(0, str(PLUGIN))
SPEC = importlib.util.spec_from_file_location("advisor_harness_hook_tests", PLUGIN / "advisor.py")
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)

POLICY = "Advisor SessionStart instructions\n" + advisor.POLICY


class HarnessHookTests(unittest.TestCase):
    def test_autoload_filename_stays_absent(self):
        self.assertFalse((PLUGIN / "hooks/hooks.json").exists())
        for relative in (".claude-plugin/plugin.json", ".zcode-plugin/plugin.json"):
            text = (PLUGIN / relative).read_text()
            self.assertNotIn("hooks-cursor.json", text)
            self.assertNotIn("hooks-codex.json", text)
        portable = (PLUGIN / "plugin.json").read_text()
        self.assertNotIn("hooks-cursor.json", portable)
        self.assertNotIn("hooks/hooks.json", portable)

    def test_cursor_manifest_runs_session_start_from_the_plugin_directory(self):
        manifest = json.loads((PLUGIN / ".cursor-plugin/plugin.json").read_text())
        self.assertEqual(manifest["hooks"], "./hooks/hooks-cursor.json")
        hooks = json.loads((PLUGIN / "hooks/hooks-cursor.json").read_text())
        self.assertEqual(hooks["version"], 1)
        self.assertEqual(set(hooks["hooks"]), {"sessionStart"})
        command = hooks["hooks"]["sessionStart"][0]
        self.assertEqual(command, {
            "command": "uv run --script ./advisor.py session-start --hook-format cursor",
            "timeout": 10,
        })
        with tempfile.TemporaryDirectory(prefix="advisor cursor hook ") as temporary:
            plugin_root = Path(temporary) / "installed plugin"
            plugin_root.symlink_to(PLUGIN, target_is_directory=True)
            completed = subprocess.run(
                command["command"], shell=True, cwd=plugin_root,
                input=json.dumps({"session_id": "unit-startup", "is_background_agent": False,
                                  "composer_mode": "agent"}),
                capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"additional_context": POLICY})

    def test_codex_manifest_runs_session_start_from_plugin_root(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text())
        relative = manifest["extensions"]["com.openai"]["hooks"]
        self.assertEqual(relative, "./hooks/hooks-codex.json")
        hooks = json.loads((PLUGIN / relative).read_text())
        self.assertEqual(set(hooks["hooks"]), {"SessionStart"})
        handler = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertEqual(handler, {
            "type": "command",
            "command": 'uv run --script "${PLUGIN_ROOT}/advisor.py" session-start',
            "timeout": 10,
        })
        with tempfile.TemporaryDirectory(prefix="advisor codex hook ") as temporary:
            plugin_root = Path(temporary) / "installed plugin"
            plugin_root.symlink_to(PLUGIN, target_is_directory=True)
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            completed = subprocess.run(
                handler["command"], shell=True, cwd=workspace,
                env=dict(os.environ, PLUGIN_ROOT=str(plugin_root)),
                input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
                capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": POLICY},
        })


if __name__ == "__main__":
    unittest.main()
