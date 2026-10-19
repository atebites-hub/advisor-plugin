"""Claude's native settings feed the existing validated profile boundary."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1] / "plugins/advisor"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("advisor_claude_configuration_tests", ROOT / "advisor.py")
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class ClaudeConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / "config.json"
        self.shared = {
            "advisors": {"claude": {"enabled": False}, "codex": {"enabled": True}},
            "usage_fallback": False,
            "timeout_seconds": 91,
            "max_consults_per_task": 2,
        }
        self.config.write_text(json.dumps(self.shared))
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ["ADVISOR_CONFIG"] = str(self.config)
        provider = patch.object(advisor, "run_provider", side_effect=AssertionError("Unexpected model call"))
        provider.start()
        self.addCleanup(provider.stop)

    def interpolate(self, **changes):
        values = {key: field["default"] for key, field in self.manifest["userConfig"].items()}
        values.update(changes)
        for name, template in self.manifest["mcpServers"]["advisor"]["env"].items():
            key = template.removeprefix("${user_config.").removesuffix("}")
            value = values[key]
            os.environ[name] = json.dumps(value) if isinstance(value, bool) else value

    def test_native_fields_preserve_profiles_and_opt_in_to_overrides(self):
        fields = self.manifest["userConfig"]
        self.assertEqual(set(fields), {"use_app_settings", "claude_enabled", "claude_model", "claude_effort",
                                       "codex_enabled", "codex_model", "codex_effort"})
        self.assertIs(fields["use_app_settings"]["default"], False)
        for provider, profile in advisor.configuration.DEFAULT_ADVISORS.items():
            for name, kind in (("enabled", "boolean"), ("model", "string"), ("effort", "string")):
                field = fields[provider + "_" + name]
                self.assertEqual(field["type"], kind)
                self.assertEqual(field["default"], profile[name])
            self.assertEqual(fields[provider + "_effort"]["options"], list(advisor.configuration.EFFORTS))

    def test_inline_server_is_complete_without_changing_shared_server(self):
        server = self.manifest["mcpServers"]["advisor"]
        self.assertEqual(server["command"], "uv")
        self.assertEqual(server["args"], ["run", "--script", "${CLAUDE_PLUGIN_ROOT}/advisor.py", "serve"])
        self.assertEqual(server["env"], {"ADVISOR_" + key.upper(): "${user_config." + key + "}"
                                         for key in self.manifest["userConfig"]})
        shared = json.loads((ROOT / ".mcp.json").read_text())
        self.assertEqual(shared, {"mcpServers": {"advisor": {"command": "uv", "args": server["args"]}}})

    def test_default_off_preserves_shared_codex_only_settings(self):
        self.interpolate(claude_model="--ignored")
        config = advisor.load_config()
        self.assertFalse(config["advisors"]["claude"]["enabled"])
        self.assertEqual(config["advisors"]["codex"],
                         {"enabled": True, "model": "gpt-6.1-sol", "effort": "max"})
        self.assertEqual(config["_configuration_source"], str(self.config))

    def test_enabled_native_profiles_replace_both_profiles_but_preserve_shared_policy(self):
        self.shared["advisors"] = {"claude": {"enabled": True}, "codex": {"enabled": False}}
        self.config.write_text(json.dumps(self.shared))
        self.interpolate(use_app_settings=True, claude_enabled=False, codex_enabled=True)
        config = advisor.load_config()
        self.assertFalse(config["advisors"]["claude"]["enabled"])
        self.assertEqual(config["advisors"]["codex"],
                         {"enabled": True, "model": "gpt-6.1-sol", "effort": "max"})
        for key in ("usage_fallback", "timeout_seconds", "max_consults_per_task"):
            self.assertEqual(config[key], self.shared[key])
        self.assertIn("Plugin app settings over", config["_configuration_source"])

    def test_invalid_native_value_fails_before_provider_call(self):
        for changes in ({"codex_model": "--invalid"}, {"codex_effort": "ultra"}, {"codex_enabled": "yes"}):
            with self.subTest(changes=changes):
                self.interpolate(use_app_settings=True, **changes)
                with self.assertRaises(advisor.AdvisorError):
                    advisor.load_config()


if __name__ == "__main__":
    unittest.main()
