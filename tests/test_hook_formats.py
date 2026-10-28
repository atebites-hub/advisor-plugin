"""Native startup formats carry the same policy without invoking an advisor."""

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
SPEC = importlib.util.spec_from_file_location("advisor_hook_format_tests", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class HookFormatTests(unittest.TestCase):
    def run_startup(self, *options):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(RUNTIME), "session-start", *options]), \
                patch.object(advisor.subprocess, "Popen") as process, \
                contextlib.redirect_stdout(output):
            self.assertEqual(advisor.main(), 0)
        process.assert_not_called()
        return json.loads(output.getvalue())

    def test_default_and_explicit_claude_formats_preserve_existing_output(self):
        expected = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                    "additionalContext": "Advisor SessionStart instructions\n" + advisor.POLICY}}
        self.assertEqual(self.run_startup(), expected)
        self.assertEqual(self.run_startup("--hook-format", "claude"), expected)

    def test_antigravity_format_injects_the_same_policy(self):
        self.assertEqual(self.run_startup("--hook-format", "antigravity"), {
            "injectSteps": [{"systemMessage": {
                "systemMessage": "Advisor SessionStart instructions\n" + advisor.POLICY,
            }}],
        })

    def test_cursor_format_returns_only_additional_context(self):
        self.assertEqual(self.run_startup("--hook-format", "cursor"), {
            "additional_context": "Advisor SessionStart instructions\n" + advisor.POLICY,
        })

    def test_explicit_hook_format_on_other_commands_fails_before_side_effects(self):
        handlers = ("build_server", "advisor_status", "consult", "run_job", "wait_for_advice",
                    "review_checkpoint", "state_root")
        for command in ("serve", "consult", "configure", "doctor", "worker", "wait", "review-checkpoint"):
            with self.subTest(command=command), contextlib.ExitStack() as stack:
                calls = [stack.enter_context(patch.object(advisor, name)) for name in handlers]
                calls.append(stack.enter_context(patch.object(advisor.configuration, "configure")))
                calls.append(stack.enter_context(patch.object(advisor.subprocess, "Popen")))
                stack.enter_context(patch.object(sys, "argv", [str(RUNTIME), command,
                                                               "--hook-format", "antigravity"]))
                output = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                self.assertEqual(advisor.main(), 1)
                self.assertIn("session-start", json.loads(output.getvalue())["error"])
                for call in calls:
                    call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
