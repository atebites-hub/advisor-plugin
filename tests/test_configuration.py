import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/advisor"))
import configuration


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "config.json"
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write(self, config):
        self.path.write_text(json.dumps(config))

    def configure(self, answers, path=None):
        with patch("builtins.input", side_effect=answers), contextlib.redirect_stdout(io.StringIO()) as output:
            result = configuration.configure(self.path if path is None else path)
        return result, output.getvalue()

    def test_defaults_are_fresh_and_partial_profiles_merge(self):
        config = {"advisors": {"claude": {"enabled": False}, "codex": {"model": "gpt-6-astra", "effort": "high"}}}
        profiles = configuration.resolved_advisors(config)
        self.assertEqual(profiles["claude"], {"enabled": False, "model": "claude-opus-5-5", "effort": "max"})
        self.assertEqual(profiles["codex"], {"enabled": True, "model": "gpt-6-astra", "effort": "high"})
        profiles["claude"]["model"] = "changed"
        self.assertEqual(configuration.resolved_advisors({})["claude"]["model"], "claude-opus-5-5")
        self.assertEqual(config["advisors"]["claude"], {"enabled": False})

    def test_config_path_uses_explicit_environment_then_default(self):
        with patch.object(Path, "home", return_value=self.root):
            self.assertEqual(configuration.config_path(), self.root / ".config/advisor/config.json")
            os.environ["ADVISOR_CONFIG"] = ""
            self.assertEqual(configuration.config_path(), self.root / ".config/advisor/config.json")
            os.environ["ADVISOR_CONFIG"] = str(self.path)
            self.assertEqual(configuration.config_path(), self.path)
            self.assertEqual(configuration.config_path(self.root / "explicit.json"), self.root / "explicit.json")

    def test_only_missing_default_configuration_is_optional(self):
        with patch.object(Path, "home", return_value=self.root):
            self.assertEqual(configuration.load_config(), {})
        with self.assertRaisesRegex(configuration.ConfigurationError, "does not exist"):
            configuration.load_config(self.path)
        os.environ["ADVISOR_CONFIG"] = str(self.path)
        with self.assertRaisesRegex(configuration.ConfigurationError, "does not exist"):
            configuration.load_config()

    def test_valid_config_keeps_unrelated_fields_and_both_disabled(self):
        config = {"unrelated": {"keep": 1}, "timeout_seconds": 30, "idle_timeout_seconds": 44,
                  "max_consults_per_task": 3, "usage_fallback": True,
                  "advisors": {name: {"enabled": False} for name in ("claude", "codex")}}
        self.write(config)
        self.assertEqual(configuration.load_config(self.path), config)
        self.assertFalse(any(profile["enabled"] for profile in configuration.resolved_advisors(config).values()))

    def test_legacy_profile_fields_accept_only_original_fixed_pairs(self):
        for provider, model in (("claude", "claude-opus-5-5"), ("codex", "gpt-6.1-sol")):
            config = {"provider": provider, "model": model}
            self.write(config)
            self.assertEqual(configuration.load_config(self.path), config)
        for config in ({"provider": "claude"}, {"model": "gpt-6.1-sol"},
                       {"provider": "codex", "model": "gpt-6-astra"}):
            self.write(config)
            with self.subTest(config=config), self.assertRaisesRegex(configuration.ConfigurationError, "two fixed advisor profiles"):
                configuration.load_config(self.path)

    def test_rejects_invalid_profile_containers_names_fields_booleans_and_effort(self):
        cases = [[], None, {"other": {}}, {"claude": None}, {"claude": {"unknown": 1}},
                 {"codex": {"enabled": 1}}, {"codex": {"enabled": "false"}},
                 {"claude": {"effort": "ultra"}}, {"codex": {"effort": []}}]
        for profiles in cases:
            with self.subTest(profiles=profiles), self.assertRaises(configuration.ConfigurationError):
                configuration.resolved_advisors({"advisors": profiles})

    def test_rejects_unsafe_ambiguous_and_cross_provider_models(self):
        for provider, model in (("claude", "opus"), ("claude", "gpt-6-astra"), ("codex", "claude-opus-5-5"),
                                ("codex", "CLAUDE-opus-5-5"), ("codex", "--model"), ("codex", "a b"),
                                ("codex", "a\x00b"), ("codex", "a/b"), ("codex", "a:b"),
                                ("codex", "a" * 129), ("codex", ""), ("codex", None),
                                ("other", "gpt-6-astra"), ("claude", "claude-")):
            with self.subTest(provider=provider, model=model), self.assertRaises(configuration.ConfigurationError):
                configuration.validate_model(provider, model)
        for provider, model in (("claude", "claude-opus-5-5-20261001"), ("codex", "gpt-6-astra"),
                                ("codex", "new-model_2.0"), ("cursor", "claude-opus-5-5-high")):
            configuration.validate_model(provider, model)

    def test_cursor_defaults_off_and_effort_must_match_the_model_id(self):
        profiles = configuration.resolved_advisors({})
        self.assertEqual(profiles["cursor"],
                         {"enabled": False, "model": "claude-opus-5-5-high", "effort": "high"})
        self.assertEqual(profiles["claude"]["effort"], "max")
        self.assertEqual(profiles["codex"]["model"], "gpt-6.1-sol")
        enabled = configuration.resolved_advisors({"advisors": {
            "cursor": {"enabled": True, "model": "claude-opus-5-5-high-fast", "effort": "high"}}})
        self.assertTrue(enabled["cursor"]["enabled"])
        extra = configuration.resolved_advisors({"advisors": {
            "cursor": {"model": "gpt-5.5-extra-high", "effort": "xhigh"}}})
        self.assertEqual(extra["cursor"]["effort"], "xhigh")
        for model, effort in (("auto", "high"), ("claude-opus-5-5-high", "max"),
                              ("claude-opus-5-5-max", "high"), ("composer-2.5", "high")):
            with self.subTest(model=model, effort=effort), self.assertRaises(configuration.ConfigurationError):
                configuration.resolved_advisors({"advisors": {"cursor": {"model": model, "effort": effort}}})

    def test_old_limits_keep_validation_messages(self):
        for key, expected in (("idle_timeout_seconds", "idle_timeout_seconds must be an integer from 1 to 3600."),
                              ("max_consults_per_task", "max_consults_per_task must be an integer from 1 to 3600."),
                              ("timeout_seconds", "timeout_seconds must be an integer from 1 to 3600 when supplied."),
                              ("usage_fallback", "usage_fallback must be a boolean.")):
            for value in (0, None, "1", []):
                self.write({key: value})
                with self.subTest(key=key, value=value), self.assertRaises(configuration.ConfigurationError) as raised:
                    configuration.load_config(self.path)
                self.assertEqual(str(raised.exception), expected)
        for key in ("idle_timeout_seconds", "max_consults_per_task", "timeout_seconds"):
            self.write({key: True})
            with self.assertRaises(configuration.ConfigurationError):
                configuration.load_config(self.path)

    def test_claude_model_syntax_matches_canonical_provider_validation(self):
        for model in ("claude-Opus-5-5", "claude-opus_5_5", "claude--opus-5-5", "claude-.opus"):
            with self.subTest(model=model), self.assertRaises(configuration.ConfigurationError):
                configuration.validate_model("claude", model)

    def test_rejects_malformed_deep_non_object_and_oversized_json(self):
        for text in ("{bad", "[]", "null", "[" * 2000 + "]" * 2000, '{"value":"' + "a" * 16384 + '"}'):
            self.path.write_text(text)
            with self.subTest(length=len(text)), self.assertRaises(configuration.ConfigurationError):
                configuration.load_config(self.path)

    def test_unreadable_config_is_reported(self):
        self.path.mkdir()
        with self.assertRaisesRegex(configuration.ConfigurationError, "Cannot read Advisor configuration as JSON"):
            configuration.load_config(self.path)

    def test_guided_setup_creates_private_file_at_new_explicit_path(self):
        target = self.root / "new" / "config.json"
        result, output = self.configure(["y", "claude-opus-5-5", "high", "y", "gpt-6-astra", "max", "n", "y"], target)
        self.assertEqual(result, 0)
        config = configuration.load_config(target)
        self.assertEqual(config["advisors"]["codex"]["model"], "gpt-6-astra")
        self.assertEqual(config["advisors"]["claude"]["effort"], "high")
        self.assertFalse(config["advisors"]["cursor"]["enabled"])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
        self.assertIn("gpt-6-astra", output)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_guided_defaults_preserve_settings_and_do_not_print_unrelated_values(self):
        self.write({"timeout_seconds": 55, "private_note": "do-not-print-this", "advisors": {"claude": {"enabled": False}}})
        self.configure(["", "", "", "", "", "y"])
        config = configuration.load_config(self.path)
        self.assertEqual(config["timeout_seconds"], 55)
        self.assertEqual(config["private_note"], "do-not-print-this")
        self.assertFalse(config["advisors"]["claude"]["enabled"])
        _, output = self.configure(["", "", "", "", "", "n"])
        self.assertNotIn("do-not-print-this", output)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_decline_and_eof_leave_existing_bytes_or_missing_file_unchanged(self):
        original = b'{"timeout_seconds":33}\n'
        self.path.write_bytes(original)
        for answers in (["n", "n", "n", "n"], [EOFError()], ["n", EOFError()]):
            with self.subTest(answers=answers):
                self.configure(answers)
                self.assertEqual(self.path.read_bytes(), original)
        self.path.unlink()
        self.configure(["n", "n", "n", "n"])
        self.assertFalse(self.path.exists())

    def test_guided_invalid_choices_can_be_corrected(self):
        self.configure(["maybe", "yes", "opus", "claude-opus-5-5", "ultra", "max", "no", "n", "yes"])
        profiles = configuration.resolved_advisors(configuration.load_config(self.path))
        self.assertTrue(profiles["claude"]["enabled"])
        self.assertFalse(profiles["codex"]["enabled"])

    def test_save_refuses_symlink_target_and_parent(self):
        actual = self.root / "actual.json"
        actual.write_text("{}")
        self.path.symlink_to(actual)
        with self.assertRaises(configuration.ConfigurationError):
            self.configure(["n", "n", "n", "y"])
        self.assertEqual(actual.read_text(), "{}")
        self.path.unlink()
        directory = self.root / "actual"
        directory.mkdir()
        link = self.root / "link"
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(configuration.ConfigurationError):
            self.configure(["n", "n", "n", "y"], link / "config.json")
        self.assertFalse((directory / "config.json").exists())

    def test_save_refuses_nonregular_or_unowned_target(self):
        self.path.mkdir()
        with self.assertRaises(configuration.ConfigurationError):
            self.configure([])
        self.path.rmdir()
        self.write({})
        with patch.object(configuration.os, "getuid", return_value=self.path.stat().st_uid + 1):
            with self.assertRaises(configuration.ConfigurationError):
                self.configure([])

    def test_save_refuses_user_owned_symlink_ancestor(self):
        actual = self.root / "actual"
        (actual / "nested").mkdir(parents=True)
        link = self.root / "link"
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(configuration.ConfigurationError):
            self.configure(["n", "n", "n", "y"], link / "nested/config.json")
        self.assertFalse((actual / "nested/config.json").exists())

    def test_guided_setup_reports_platform_without_ownership_checks(self):
        self.write({})
        with patch.object(configuration.os, "getuid", None):
            with self.assertRaisesRegex(configuration.ConfigurationError, "ownership checks"):
                self.configure([])

    def test_save_refuses_concurrent_contents_identity_or_creation(self):
        for change in ("write", "replace", "create"):
            with self.subTest(change=change):
                if change == "create":
                    self.path.unlink(missing_ok=True)
                else:
                    self.path.write_text("{}")
                answers = iter(["n", "n", "n", "y"])

                def answer(_prompt):
                    value = next(answers)
                    if value == "y":
                        if change == "replace":
                            replacement = self.root / "replacement.json"
                            replacement.write_text("{}")
                            replacement.replace(self.path)
                        else:
                            self.path.write_text('{"concurrent":true}')
                    return value

                with patch("builtins.input", side_effect=answer), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(configuration.ConfigurationError, "changed"):
                        configuration.configure(self.path)
                if change != "replace":
                    self.assertEqual(json.loads(self.path.read_text()), {"concurrent": True})

    def test_atomic_replace_failure_preserves_original_and_removes_temporary_file(self):
        original = b'{"unrelated":"keep"}\n'
        self.path.write_bytes(original)
        with patch.object(configuration.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaisesRegex(configuration.ConfigurationError, "Cannot safely save"):
                self.configure(["n", "n", "n", "y"])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
