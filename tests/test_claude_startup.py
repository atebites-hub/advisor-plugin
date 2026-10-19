"""Claude registers the shared startup policy through its native manifest."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / "plugins/advisor"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("advisor_claude_startup_tests", ROOT / "advisor.py")
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class ClaudeStartupTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())

    def test_native_manifest_registers_only_shared_session_start(self):
        self.assertEqual(self.manifest.get("hooks"), {
            "SessionStart": [{"hooks": [{
                "type": "command",
                "command": 'uv run --script "${CLAUDE_PLUGIN_ROOT}/advisor.py" session-start',
                "timeout": 10,
            }]}],
        })
        for relative in ("plugin.json", "mcp.json"):
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", (ROOT / relative).read_text())

    def test_registered_command_uses_absolute_root_from_an_unrelated_directory(self):
        hook = self.manifest["hooks"]["SessionStart"][0]["hooks"][0]
        with tempfile.TemporaryDirectory(prefix="advisor claude startup ") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            plugin_root = Path(temporary) / "installed plugin"
            plugin_root.symlink_to(ROOT, target_is_directory=True)
            environment = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root))
            completed = subprocess.run(hook["command"], shell=True, cwd=workspace, env=environment,
                                       input=json.dumps({"hook_event_name": "SessionStart", "source": "startup",
                                                         "session_id": "unit-startup", "cwd": str(workspace)}),
                                       capture_output=True, text=True, timeout=hook["timeout"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {
            "hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "Advisor SessionStart instructions\n" + advisor.POLICY},
        })


if __name__ == "__main__":
    unittest.main()
