import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_startup_tests", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class StartupTests(unittest.TestCase):
    def test_skill_fits_native_plugin_instruction_budget(self):
        skill = RUNTIME.parent / "skills/advisor/SKILL.md"
        self.assertLessEqual(len(skill.read_bytes()), 8000)

    def test_session_start_injects_actionable_context_without_starting_a_process(self):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(RUNTIME), "session-start"]), \
                patch.object(advisor.subprocess, "Popen") as process, \
                contextlib.redirect_stdout(output):
            self.assertEqual(advisor.main(), 0)
        context = json.loads(output.getvalue())["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "SessionStart")
        policy = context["additionalContext"]
        self.assertTrue(policy.startswith("Advisor SessionStart instructions"))
        for required in ("uncertain", "claude", "codex", "skill", "consult_advisor", "read_advice",
                         "before substantive work", "early review", "final review",
                         "before declaring the task done", "retrieve completed advice",
                         "dependent work", "completion_watcher", "run_in_background",
                         "independent edits", "wake an idle session", "dependent_paths",
                         "advisor_status", "across turns", "failed or unavailable"):
            self.assertIn(required, policy)
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
