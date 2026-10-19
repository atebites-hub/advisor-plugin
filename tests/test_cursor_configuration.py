"""Cursor variables feed the shared profile validator without model calls."""

import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "plugins/advisor"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("advisor_cursor_configuration_tests", ROOT / "advisor.py")
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class CursorConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / ".cursor-plugin/plugin.json").read_text())
        self.server = json.loads((ROOT / ".cursor-plugin/mcp.json").read_text())["mcpServers"]["advisor"]
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.config = Path(temporary.name) / "config.json"
        self.config.write_text(json.dumps({
            "advisors": {"claude": {"enabled": False}, "codex": {"effort": "high"}},
            "usage_fallback": False,
            "timeout_seconds": 42,
        }))

    def interpolated(self, **changes):
        values = {name: field["default"] for name, field in self.manifest["variables"]["properties"].items()}
        values.update(changes)
        return {name: re.sub(r"\$\{([^}]+)\}", lambda match: values[match[1]], value)
                for name, value in self.server["env"].items()}

    def test_variables_declare_all_mcp_settings_with_valid_string_defaults(self):
        schema = self.manifest["variables"]
        self.assertEqual(schema["type"], "object")
        fields = schema["properties"]
        expected = {"ADVISOR_USE_APP_SETTINGS"}
        for provider in ("CLAUDE", "CODEX"):
            expected.update("ADVISOR_" + provider + "_" + suffix for suffix in ("ENABLED", "MODEL", "EFFORT"))
        self.assertEqual(set(fields), expected)
        self.assertEqual(set(self.server["env"]), expected)
        self.assertEqual(set(schema["required"]), expected)
        for name, field in fields.items():
            with self.subTest(name=name):
                self.assertEqual(field["type"], "string")
                self.assertIsInstance(field["default"], str)
                self.assertEqual(self.server["env"][name], "${" + name + "}")
                if name.endswith("ENABLED") or name == "ADVISOR_USE_APP_SETTINGS":
                    self.assertEqual(field["enum"], ["true", "false"])
                if name.endswith("EFFORT"):
                    self.assertEqual(field["enum"], list(advisor.configuration.EFFORTS))
                if "enum" in field:
                    self.assertIn(field["default"], field["enum"])
        self.assertEqual(fields["ADVISOR_USE_APP_SETTINGS"]["default"], "false")
        self.assertEqual(self.manifest["mcpServers"], "./.cursor-plugin/mcp.json")
        self.assertEqual(self.server["args"], ["run", "--script", "${CURSOR_PLUGIN_ROOT}/advisor.py", "serve"])

    def test_default_opt_out_keeps_shared_configuration_authoritative(self):
        with patch.dict(os.environ, self.interpolated(), clear=True):
            config = advisor.load_config(self.config)
        self.assertFalse(config["advisors"]["claude"]["enabled"])
        self.assertEqual(config["advisors"]["codex"]["effort"], "high")
        self.assertNotIn("Plugin app settings", config["_configuration_source"])

    def test_opted_in_defaults_preserve_existing_max_profiles(self):
        with patch.dict(os.environ, self.interpolated(ADVISOR_USE_APP_SETTINGS="true"), clear=True):
            config = advisor.load_config(self.config)
        self.assertEqual(config["advisors"], advisor.configuration.DEFAULT_ADVISORS)
        self.assertFalse(config["usage_fallback"])
        self.assertEqual(config["timeout_seconds"], 42)

    def test_configured_codex_only_profile_reaches_status_and_selection(self):
        env = self.interpolated(ADVISOR_USE_APP_SETTINGS="true", ADVISOR_CLAUDE_ENABLED="false",
                                ADVISOR_CODEX_MODEL="gpt-6.1-sol", ADVISOR_CODEX_EFFORT="max")
        with patch.dict(os.environ, env, clear=True), patch.object(advisor.shutil, "which", return_value=None), \
                patch.object(advisor, "run_provider", side_effect=AssertionError("Unexpected provider call")):
            status = advisor.advisor_status(self.config)
            config = advisor.load_config(self.config)
            self.assertEqual(advisor.select_provider({"provider": "codex"}, config), "codex")
            with self.assertRaisesRegex(advisor.AdvisorError, "disabled"):
                advisor.select_provider({"provider": "claude"}, config)
        self.assertFalse(status["advisors"]["claude"]["enabled"])
        self.assertEqual(status["advisors"]["codex"],
                         {"enabled": True, "model": "gpt-6.1-sol", "effort": "max", "installed": False})
        self.assertIn("Plugin app settings", status["configuration_source"])

    def test_missing_or_unresolved_opted_in_values_fail_closed(self):
        env = self.interpolated(ADVISOR_USE_APP_SETTINGS="true")
        for name in env.keys() - {"ADVISOR_USE_APP_SETTINGS"}:
            for value in (None, "${" + name + "}", ""):
                with self.subTest(name=name, value=value):
                    invalid = dict(env)
                    if value is None:
                        invalid.pop(name)
                    else:
                        invalid[name] = value
                    with patch.dict(os.environ, invalid, clear=True), self.assertRaises(advisor.AdvisorError):
                        advisor.load_config(self.config)
        for value in ("yes", "True", "1", "${ADVISOR_USE_APP_SETTINGS}"):
            with self.subTest(master=value), patch.dict(os.environ, env | {"ADVISOR_USE_APP_SETTINGS": value}, clear=True), \
                    self.assertRaises(advisor.AdvisorError):
                advisor.load_config(self.config)


if __name__ == "__main__":
    unittest.main()
