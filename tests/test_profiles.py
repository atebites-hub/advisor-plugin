"""Configured profiles are user authority, never consultation input."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_profile_tests", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "state"
        self.config = self.root / "config.json"
        self.config.write_text("{}")
        self.request = dict(provider="codex", workspace=str(self.root), host="test",
                            session_id="worker", task_id="task", stage="before_task",
                            question="Review the approach.", context="Evidence.")
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("ADVISOR_ACTIVE", "ADVISOR_USE_APP_SETTINGS"):
            os.environ.pop(name, None)
        os.environ["ADVISOR_CONFIG"] = str(self.config)
        self.addCleanup(advisor.WORKERS.clear)

    def configured(self, **values):
        self.config.write_text(json.dumps(values))
        return self.config

    def test_custom_model_effort_and_changed_profile_isolate_memory_and_budget(self):
        with patch.object(advisor, "run_provider", return_value=("Advice.", "native-1")) as run:
            initial = advisor.consult(self.request, config_path=self.config, state_dir=self.state)
            self.configured(max_consults_per_task=1, advisors={"codex": {"model": "gpt-6-astra", "effort": "high"}})
            custom = advisor.consult(self.request, config_path=self.config, state_dir=self.state)
            cached = advisor.consult(self.request, config_path=self.config, state_dir=self.state)
        self.assertEqual(initial["model"], "gpt-6.1-sol")
        self.assertEqual((custom["model"], custom["effort"]), ("gpt-6-astra", "high"))
        self.assertFalse(custom["cached"])
        self.assertTrue(cached["cached"])
        self.assertEqual(custom["remaining_consults"], 0)
        self.assertEqual(run.call_count, 2)
        self.assertIsNone(run.call_args.args[4])
        self.assertEqual(run.call_args.kwargs["effort"], "high")

    def test_default_session_identity_remains_byte_exact(self):
        with patch.object(advisor, "run_provider", return_value=("Advice.", "native-1")):
            advisor.consult(self.request, config_path=self.config, state_dir=self.state)
        expected = hashlib.sha256(json.dumps([str(self.root), "test", "worker", "task", "codex", "gpt-6.1-sol", "max"]).encode()).hexdigest()
        self.assertTrue((self.state / expected / "session.sqlite3").is_file())

    def test_disabled_and_request_overrides_reject_before_native_capture(self):
        self.configured(advisors={"codex": {"enabled": False}})
        with patch.object(advisor, "capture_zcode_context") as capture:
            with self.assertRaisesRegex(advisor.AdvisorError, "disabled"):
                advisor.prepare_request(self.request, {"com.zcode/request-context": {}}, state_dir=self.state)
            self.configured()
            for key in ("model", "effort", "advisors", "config", "config_path", "usage_fallback"):
                with self.subTest(key=key), self.assertRaisesRegex(advisor.AdvisorError, "configuration"):
                    advisor.prepare_request(self.request | {key: "override"}, {"com.zcode/request-context": {}}, state_dir=self.state)
        capture.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_direct_submission_rejects_disabled_before_context_or_job(self):
        self.configured(advisors={"codex": {"enabled": False}})
        with patch.object(advisor, "context_packet") as packet, patch.object(advisor.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(advisor.AdvisorError, "disabled"):
                advisor.submit_consultation(self.request, config_path=self.config, state_dir=self.state)
        packet.assert_not_called()
        launch.assert_not_called()

    def test_status_supports_all_disabled_without_auth_or_model_calls(self):
        self.configured(advisors={name: {"enabled": False} for name in ("claude", "codex")})
        with patch.object(advisor.shutil, "which", return_value=None):
            result = advisor.advisor_status()
        self.assertFalse(any(value["enabled"] for value in result["advisors"].values()))
        self.assertIn("configuration_source", result)

    def app_settings(self, **changes):
        values = {"ADVISOR_USE_APP_SETTINGS": "true",
                  "ADVISOR_CLAUDE_ENABLED": "false", "ADVISOR_CLAUDE_MODEL": "claude-opus-5-5", "ADVISOR_CLAUDE_EFFORT": "max",
                  "ADVISOR_CODEX_ENABLED": "true", "ADVISOR_CODEX_MODEL": "gpt-6-astra", "ADVISOR_CODEX_EFFORT": "high",
                  "ADVISOR_CURSOR_ENABLED": "false", "ADVISOR_CURSOR_MODEL": "claude-opus-5-5-high", "ADVISOR_CURSOR_EFFORT": "high"}
        os.environ.update(values | changes)

    def test_app_profiles_override_only_profiles_and_report_the_layered_source(self):
        self.configured(usage_fallback=True, timeout_seconds=33, max_consults_per_task=2,
                        advisors={"codex": {"enabled": False}})
        self.app_settings()
        config = advisor.load_config()
        self.assertTrue(config["advisors"]["codex"]["enabled"])
        self.assertEqual(config["advisors"]["codex"]["model"], "gpt-6-astra")
        self.assertEqual(config["timeout_seconds"], 33)
        self.assertTrue(config["usage_fallback"])
        self.assertEqual(config["max_consults_per_task"], 2)
        self.assertIn("app", advisor.advisor_status()["configuration_source"])

    def test_disabled_app_settings_ignore_remaining_invalid_environment(self):
        self.app_settings(ADVISOR_USE_APP_SETTINGS="false", ADVISOR_CODEX_MODEL="--unsafe")
        self.assertEqual(advisor.load_config()["advisors"]["codex"]["model"], "gpt-6.1-sol")
        os.environ.pop("ADVISOR_USE_APP_SETTINGS")
        self.assertEqual(advisor.load_config()["advisors"]["codex"]["model"], "gpt-6.1-sol")

    def test_enabled_app_settings_require_complete_strict_valid_values(self):
        for key, value in (("ADVISOR_USE_APP_SETTINGS", "yes"), ("ADVISOR_CODEX_ENABLED", "1"),
                           ("ADVISOR_CODEX_MODEL", "--unsafe"), ("ADVISOR_CODEX_EFFORT", "ultra")):
            with self.subTest(key=key):
                self.app_settings(**{key: value})
                with self.assertRaises(advisor.AdvisorError):
                    advisor.load_config()
        self.app_settings()
        os.environ.pop("ADVISOR_CLAUDE_MODEL")
        with self.assertRaises(advisor.AdvisorError):
            advisor.load_config()
        self.app_settings()
        self.configured(advisors={"codex": {"effort": "wrong"}})
        with self.assertRaises(advisor.AdvisorError):
            advisor.load_config()

    def test_custom_provider_argv_and_claude_response_model(self):
        command = advisor.provider_command("codex", "gpt-6-astra", None, effort="high")
        self.assertIn('model_reasoning_effort="high"', command)
        command = advisor.provider_command("claude", "claude-sonnet-5-5", None, effort="medium")
        self.assertEqual(command[command.index("--effort") + 1], "medium")
        response = dict(type="result", result="Advice.", session_id="native-1", modelUsage={"claude-sonnet-5-5": {}})
        self.assertEqual(advisor.parse_response("claude", json.dumps(response), expected_model="claude-sonnet-5-5"), ("Advice.", "native-1"))
        with self.assertRaises(advisor.AdvisorError):
            advisor.parse_response("claude", json.dumps(response), expected_model="claude-opus-5-5")

    def test_frozen_resolved_config_is_used_after_user_file_changes(self):
        self.configured(advisors={"codex": {"model": "gpt-6-astra", "effort": "high"}})
        config = advisor.load_config(self.config)
        prepared = advisor.prepare_request(self.request, {}, _config=config)
        self.configured(advisors={"codex": {"enabled": False}})
        with patch.object(advisor, "load_config", side_effect=AssertionError("configuration was reread")), \
                patch.object(advisor, "run_provider", return_value=("Advice.", "native-1")) as run:
            advisor.consult(prepared, state_dir=self.state, _config=config)
        self.assertEqual(run.call_args.args[1], "gpt-6-astra")

    def test_changed_effort_alone_starts_a_fresh_session(self):
        with patch.object(advisor, "run_provider", return_value=("Advice.", "native-1")) as run:
            advisor.consult(self.request, config_path=self.config, state_dir=self.state)
            self.configured(advisors={"codex": {"effort": "high"}})
            result = advisor.consult(self.request, config_path=self.config, state_dir=self.state)
        self.assertEqual(run.call_count, 2)
        self.assertIsNone(run.call_args.args[4])
        self.assertFalse(result["cached"])

    def test_claude_launch_passes_exact_effort_to_argv_environment_and_quota_proof(self):
        executable = self.root / "claude"
        report = self.root / "launch.json"
        executable.write_text(f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
                              f"Path({str(report)!r}).write_text(json.dumps(dict(args=sys.argv, effort=os.environ['CLAUDE_CODE_EFFORT_LEVEL'])))\n"
                              "sys.stdin.read()\n"
                              "print(json.dumps(dict(type='result', result='Advice.', session_id='native-1', modelUsage={'claude-sonnet-5-5':{}})))\n")
        executable.chmod(0o700)
        with patch.object(advisor.shutil, "which", return_value=str(executable)), \
                patch.object(advisor, "detect_usage", return_value=None) as detect:
            result = advisor.run_provider("claude", "claude-sonnet-5-5", "Evidence.", self.root, None, 10,
                                          effort="medium", usage_fallback=True)
        recorded = json.loads(report.read_text())
        self.assertEqual(recorded["effort"], "medium")
        self.assertEqual(recorded["args"][recorded["args"].index("--effort") + 1], "medium")
        self.assertEqual(detect.call_args.kwargs["model"], "claude-sonnet-5-5")
        self.assertEqual(detect.call_args.kwargs["effort"], "medium")
        self.assertEqual(result, ("Advice.", "native-1"))

    def test_disabled_alternate_never_launches_after_verified_exhaustion(self):
        self.configured(usage_fallback=True, advisors={"claude": {"enabled": False}})
        exhausted = advisor.UsageExhausted({"message": "Verified synthetic exhaustion."})
        with patch.object(advisor, "run_provider", side_effect=exhausted) as run:
            with self.assertRaises(advisor.AdvisorError):
                advisor.consult(self.request, config_path=self.config, state_dir=self.state)
        run.assert_called_once()

    def test_verified_exhaustion_uses_configured_alternate_profile_and_same_context(self):
        self.configured(usage_fallback=True,
                        advisors={"codex": {"model": "gpt-6-astra", "effort": "high"}})
        exhausted = advisor.UsageExhausted({"code": "usage_limit_reached",
                                           "message": "Verified synthetic exhaustion."})
        with patch.object(advisor, "run_provider", side_effect=[exhausted, ("Advice.", "native-2")]) as run:
            result = advisor.consult(self.request | {"provider": "claude"},
                                     config_path=self.config, state_dir=self.state)
        self.assertEqual(run.call_count, 2)
        primary, alternate = run.call_args_list
        self.assertEqual(alternate.args[:2], ("codex", "gpt-6-astra"))
        self.assertEqual(alternate.kwargs["effort"], "high")
        self.assertEqual(primary.args[2], alternate.args[2])
        self.assertEqual((result["provider"], result["model"], result["effort"]),
                         ("codex", "gpt-6-astra", "high"))
        self.assertEqual(result["requested_provider"], "claude")
        self.assertEqual([(attempt["provider"], attempt["model"], attempt["effort"], attempt["status"])
                          for attempt in result["provider_attempts"]],
                         [("claude", "claude-opus-5-5", "max", "usage_exhausted"),
                          ("codex", "gpt-6-astra", "high", "completed")])

    def test_cursor_stays_opt_in_and_outside_usage_fallback(self):
        self.assertFalse(advisor.load_config(self.config)["advisors"]["cursor"]["enabled"])
        self.assertEqual(advisor.load_config(self.config)["advisors"]["cursor"]["model"], "claude-opus-5-5-high")
        with patch.object(advisor.shutil, "which", return_value=None):
            status = advisor.advisor_status(self.config)
        self.assertFalse(status["advisors"]["cursor"]["installed"])
        self.configured(usage_fallback=True, advisors={"cursor": {"enabled": True}})
        exhausted = advisor.UsageExhausted({"message": "Verified synthetic exhaustion."})
        with patch.object(advisor, "run_provider", side_effect=exhausted) as run:
            with self.assertRaisesRegex(advisor.AdvisorError, "no enabled alternate"):
                advisor.consult(self.request | {"provider": "cursor"}, config_path=self.config, state_dir=self.state)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[:2], ("cursor", "claude-opus-5-5-high"))
        self.assertEqual(run.call_args.kwargs["effort"], "high")
        with patch.object(advisor, "run_provider", side_effect=[exhausted, ("Advice.", "native-2")]) as run:
            result = advisor.consult(self.request | {"provider": "claude"},
                                     config_path=self.config, state_dir=self.state)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["claude", "codex"])
        self.assertEqual(result["provider"], "codex")
        with patch.object(advisor, "run_provider", side_effect=[exhausted, ("Advice.", "native-3")]) as run:
            result = advisor.consult(self.request | {"question": "Review the Codex handoff."},
                                     config_path=self.config, state_dir=self.state)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["codex", "claude"])
        self.assertEqual(result["provider"], "claude")
        self.assertIsNone(advisor.detect_usage(
            "cursor", "You've hit your usage limit.", 1, model="claude-opus-5-5-high", effort="high"))

    def test_attempt_journals_are_separate_for_changed_profiles(self):
        with patch.object(advisor, "run_provider", return_value=("Advice.", "native-1")):
            for model in ("gpt-6.1-sol", "gpt-6-astra"):
                self.configured(usage_fallback=True, advisors={"codex": {"model": model}})
                advisor.consult(self.request, config_path=self.config, state_dir=self.state)
        self.assertEqual(len(list((self.state / "attempts").glob("*.json"))), 2)

    def submit(self):
        with patch.object(advisor.subprocess, "Popen") as launch:
            launch.return_value.poll.return_value = None
            return advisor.submit_consultation(self.request, config_path=self.config, state_dir=self.state)

    def test_frozen_profiles_ignore_later_changes_disable_and_gui_environment(self):
        self.configured(advisors={"codex": {"model": "gpt-6-astra", "effort": "high"}, "claude": {"enabled": False}})
        job = self.submit()
        frozen = json.loads((Path(job["advice_path"]).parent / "config.json").read_text())
        self.assertEqual(frozen["schema_version"], 2)
        self.assertFalse(frozen["advisors"]["claude"]["enabled"])
        self.config.unlink()
        os.environ.update(ADVISOR_USE_APP_SETTINGS="true", ADVISOR_CODEX_ENABLED="false", ADVISOR_CLAUDE_ENABLED="false")
        with patch.object(advisor, "run_provider", return_value=("Saved advice.", "native-1")) as run:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        self.assertEqual(run.call_args.args[1], "gpt-6-astra")
        self.assertEqual(run.call_args.kwargs["effort"], "high")
        self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["advice"], "Saved advice.")

    def test_job_dedupe_tracks_only_effective_fallback_authority(self):
        first = self.submit()
        self.configured(advisors={"claude": {"model": "claude-sonnet-5-5"}})
        self.assertEqual(first["job_id"], self.submit()["job_id"])
        self.configured(usage_fallback=True, advisors={"claude": {"model": "claude-sonnet-5-5"}})
        fallback = self.submit()
        self.assertNotEqual(first["job_id"], fallback["job_id"])
        self.configured(usage_fallback=True, advisors={"claude": {"model": "claude-opus-5-5"}})
        self.assertNotEqual(fallback["job_id"], self.submit()["job_id"])

    def test_schema_one_jobs_keep_historic_profiles_and_saved_fallback(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent
        (directory / "config.json").write_text(json.dumps(dict(schema_version=1, provider="codex", model="gpt-6.1-sol", usage_fallback=True, timeout_seconds=19, idle_timeout_seconds=13, max_consults_per_task=2)))
        self.configured(advisors={"codex": {"model": "gpt-6-astra", "enabled": False}})
        with patch.object(advisor, "run_provider", return_value=("Old advice.", "native-1")) as run:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        self.assertEqual(run.call_args.args[1], "gpt-6.1-sol")
        self.assertEqual(run.call_args.args[5], 19)
        self.assertTrue(run.call_args.kwargs["usage_fallback"])

    def test_incomplete_frozen_profiles_never_silently_use_defaults(self):
        job = self.submit()
        path = Path(job["advice_path"]).parent / "config.json"
        frozen = json.loads(path.read_text())
        del frozen["advisors"]["codex"]["effort"]
        path.write_text(json.dumps(frozen))
        with patch.object(advisor, "run_provider") as run:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        run.assert_not_called()

    def test_recursive_native_admission_never_captures(self):
        os.environ["ADVISOR_ACTIVE"] = "1"
        with patch.object(advisor, "capture_zcode_context") as capture:
            with self.assertRaisesRegex(advisor.AdvisorError, "recursion"):
                advisor.prepare_request(self.request | {"dependent_paths": []}, {"com.zcode/request-context": {}})
        capture.assert_not_called()

    def test_configure_cli_forwards_explicit_path_to_user_wizard(self):
        with patch.object(sys, "argv", ["advisor.py", "configure", "--config", str(self.config)]), \
                patch.object(advisor.configuration, "configure", return_value=0) as configure:
            self.assertEqual(advisor.main(), 0)
        configure.assert_called_once_with(self.config)


if __name__ == "__main__":
    unittest.main()
