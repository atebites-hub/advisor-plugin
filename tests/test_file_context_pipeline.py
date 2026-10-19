import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_file_context_pipeline", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


@unittest.skipIf(os.name == "nt", "Secure selected-file capture requires POSIX directory descriptors")
class FileContextPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.state = self.root / "state"
        self.config = self.root / "config.json"
        self.config.write_text("{}")
        self.request = {
            "provider": "codex", "workspace": str(self.workspace), "host": "claude",
            "session_id": "worker-session", "task_id": "saved-file-review",
            "stage": "during_task", "question": "Review the saved implementation and test results.",
            "context": "The selected files are the saved deliverable and its evidence.",
            "context_files": ["implementation.py"],
        }
        self.source = self.workspace / "implementation.py"
        self.source.write_text("original implementation\n")
        environment = patch.dict(os.environ, {"ADVISOR_CONFIG": str(self.config), "ADVISOR_USE_APP_SETTINGS": "false"})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("ADVISOR_ACTIVE", None)
        self.launch_patch = patch.object(advisor.subprocess, "Popen")
        self.launch = self.launch_patch.start()
        self.addCleanup(self.launch_patch.stop)
        self.launch.return_value.pid = os.getpid()
        self.launch.return_value.poll.return_value = None
        self.addCleanup(advisor.WORKERS.clear)

    def consult(self, **changes):
        return advisor.consult(self.request | changes, config_path=self.config, state_dir=self.state)

    def submit(self, **changes):
        return advisor.submit_consultation(self.request | changes, config_path=self.config, state_dir=self.state)

    def packet(self, provider):
        return json.loads(provider.call_args.args[2].split("Context packet:\n", 1)[1])

    @patch.object(advisor, "run_provider", return_value=("Keep the saved behavior.", "fake-advisor-session"))
    def test_provider_receives_literal_unicode_crlf_and_redacted_file_metadata(self, provider):
        secret = "sk-" + "a" * 48
        original = "# café 🚗\r\nAPI_KEY=" + secret + "\r\nassert 'λ' == 'λ'\r\n"
        self.source.write_bytes(original.encode("utf-8"))
        tests = self.workspace / "tests.txt"
        tests.write_bytes("2 tests passed\r\n".encode("utf-8"))

        result = self.consult(context_files=["tests.txt", "implementation.py"])

        snapshot = self.packet(provider)["file_context"]
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["binding"], {
            key: self.request[key] for key in ("workspace", "host", "session_id", "task_id")
        })
        self.assertEqual([entry["path"] for entry in snapshot["files"]], ["implementation.py", "tests.txt"])
        first, second = snapshot["files"]
        expected = advisor.redact(original)
        self.assertEqual(first["content"], expected)
        self.assertIn("# café 🚗\r\n", first["content"])
        self.assertNotIn(secret, first["content"])
        self.assertEqual(first["sha256"], hashlib.sha256(expected.encode("utf-8")).hexdigest())
        self.assertEqual(first["bytes"], len(expected.encode("utf-8")))
        self.assertTrue(first["redacted"])
        self.assertEqual(second["content"], "2 tests passed\r\n")
        self.assertFalse(second["redacted"])
        transfer = result["context_transfer"]
        self.assertEqual(transfer["mode"], "supplied_packet")
        self.assertRegex(transfer["file_context_id"], r"^[a-f0-9]{64}$")
        self.assertEqual(transfer["files"], [
            {key: value for key, value in entry.items() if key != "content"}
            for entry in snapshot["files"]
        ])
        for path in self.state.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret.encode(), path.read_bytes())
        provider.assert_called_once()
        self.launch.assert_not_called()

    @patch.object(advisor, "run_provider", return_value=("The whole file arrived.", "fake-advisor-session"))
    def test_selected_evidence_larger_than_request_limit_reaches_provider_in_full(self, provider):
        content = "α" * (advisor.MAX_INPUT_BYTES // 2 + 100)
        self.source.write_bytes(content.encode("utf-8"))
        self.assertLess(len(json.dumps(self.request).encode()), advisor.MAX_INPUT_BYTES)
        self.assertGreater(self.source.stat().st_size, advisor.MAX_INPUT_BYTES)

        result = self.consult()

        entry = self.packet(provider)["file_context"]["files"][0]
        self.assertEqual(entry["content"], content)
        self.assertEqual(entry["bytes"], len(content.encode("utf-8")))
        self.assertEqual(result["context_transfer"]["files"][0]["sha256"],
                         hashlib.sha256(content.encode("utf-8")).hexdigest())

    @patch.object(advisor, "run_provider", return_value=("Read the frozen original.", "fake-advisor-session"))
    def test_background_worker_uses_frozen_files_after_originals_are_changed_or_removed(self, provider):
        extra = self.workspace / "tests.txt"
        extra.write_bytes(b"original test result\r\n")
        job = self.submit(context_files=["implementation.py", "tests.txt"])
        self.assertEqual(job["status"], "pending")
        directory = Path(job["advice_path"]).parent
        stored = json.loads((directory / "request.json").read_text())["request"]
        self.assertNotIn("context_files", stored)
        snapshot_id = stored["file_context_id"]
        self.assertRegex(snapshot_id, r"^[a-f0-9]{64}$")
        self.assertEqual(job["context_transfer"]["file_context_id"], snapshot_id)
        self.assertNotIn("original implementation", (directory / "request.json").read_text())
        frozen = self.state / "file-contexts" / (snapshot_id + ".json")
        self.assertTrue(frozen.is_file())
        self.source.write_text("replacement after submission\n")
        extra.unlink()

        with patch.object(advisor, "capture_file_context", side_effect=AssertionError("Worker reread original files")):
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)

        entries = self.packet(provider)["file_context"]["files"]
        self.assertEqual([entry["content"] for entry in entries],
                         ["original implementation\n", "original test result\r\n"])
        result = advisor.read_advice(job["job_id"], state_dir=self.state)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["context_transfer"]["file_context_id"], snapshot_id)
        self.assertEqual(result["advice"], "Read the frozen original.")
        provider.assert_called_once()
        self.launch.assert_called_once()

    @patch.object(advisor, "run_provider", return_value=("Read the entire packet.", "fake-advisor-session"))
    def test_background_worker_accepts_frozen_envelope_larger_than_client_input_limit(self, provider):
        (self.workspace / "a").write_text("saved evidence\n")
        request = self.request | {"context_files": ["a"], "context": "x"}
        request["context"] += "x" * (advisor.MAX_INPUT_BYTES - len(json.dumps(request).encode()))
        self.assertEqual(len(json.dumps(request).encode()), advisor.MAX_INPUT_BYTES)
        for method in (advisor.consult, advisor.submit_consultation):
            for fields in ({}, {"_input_validated": True}):
                with self.subTest(method=method.__name__, fields=fields), self.assertRaisesRegex(advisor.AdvisorError, "1 MiB"):
                    method(request | {"context": request["context"] + "x"} | fields,
                           config_path=self.config, state_dir=self.state)
        self.assertFalse(self.state.exists())
        self.launch.assert_not_called()

        job = advisor.submit_consultation(request, config_path=self.config, state_dir=self.state)
        stored = json.loads((Path(job["advice_path"]).parent / "request.json").read_text())["request"]
        self.assertGreater(len(json.dumps(stored).encode()), advisor.MAX_INPUT_BYTES)
        with self.assertRaisesRegex(advisor.AdvisorError, "1 MiB"):
            advisor.consult(stored, config_path=self.config, state_dir=self.state)
        (self.workspace / "a").unlink()

        self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)

        packet = self.packet(provider)
        self.assertEqual(packet["context"], request["context"])
        self.assertEqual(packet["file_context"]["files"][0]["content"], "saved evidence\n")
        self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "completed")
        provider.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_worker_revalidates_fields_scope_and_assembled_limit_after_client_size_check(self, provider):
        for index, (changes, error) in enumerate([
            ({"stage": "invalid"}, "Unknown consultation stage"),
            ({"context": ""}, "context must be a nonempty string"),
            ({"host": "another-host"}, "does not belong"),
            ({"context": "x" * advisor.MAX_CONTEXT_BYTES}, "8 MiB"),
        ]):
            with self.subTest(changes=list(changes)):
                job = self.submit(question=f"Review variant {index}")
                path = Path(job["advice_path"]).parent / "request.json"
                payload = json.loads(path.read_text())
                payload["request"].update(changes)
                path.write_text(json.dumps(payload))
                self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
                result = advisor.read_advice(job["job_id"], state_dir=self.state)
                self.assertEqual(result["status"], "failed")
                self.assertIn(error, result["error"])
        provider.assert_not_called()

    def test_content_changes_create_distinct_jobs_and_unchanged_files_deduplicate(self):
        first = self.submit()
        duplicate = self.submit()
        self.source.write_text("revised implementation\n")
        revised = self.submit()
        revised_duplicate = self.submit()

        self.assertEqual(first["job_id"], duplicate["job_id"])
        self.assertEqual(revised["job_id"], revised_duplicate["job_id"])
        self.assertNotEqual(first["job_id"], revised["job_id"])
        self.assertNotEqual(first["context_transfer"]["file_context_id"],
                            revised["context_transfer"]["file_context_id"])
        self.assertEqual(self.launch.call_count, 2)

    @patch.object(advisor, "run_provider", return_value=("Advice", "fake-advisor-session"))
    def test_direct_consult_cache_changes_with_saved_contents(self, provider):
        first = self.consult()
        duplicate = self.consult()
        self.source.write_text("changed direct-call evidence\n")
        changed = self.consult()

        self.assertFalse(first["cached"])
        self.assertTrue(duplicate["cached"])
        self.assertFalse(changed["cached"])
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(self.packet(provider)["file_context"]["files"][0]["content"],
                         "changed direct-call evidence\n")

    @patch.object(advisor, "run_provider")
    def test_tampered_snapshot_fails_background_job_without_provider_call(self, provider):
        job = self.submit()
        snapshot = self.state / "file-contexts" / (job["context_transfer"]["file_context_id"] + ".json")
        snapshot.write_text("{}")

        self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)

        result = advisor.read_advice(job["job_id"], state_dir=self.state)
        self.assertEqual(result["status"], "failed")
        self.assertIn("integrity", result["error"])
        provider.assert_not_called()
        self.launch.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_frozen_reference_cannot_cross_any_scope_boundary(self, provider):
        frozen = advisor.freeze_file_context(advisor.validate_request(self.request), self.state)
        alternate = self.root / "other-workspace"
        alternate.mkdir()
        for changes in ({"workspace": str(alternate)}, {"host": "cursor"},
                        {"session_id": "another-session"}, {"task_id": "another-task"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(advisor.AdvisorError, "does not belong"):
                advisor.consult(frozen | changes, config_path=self.config, state_dir=self.state)
        provider.assert_not_called()
        self.launch.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_invalid_selection_fails_before_provider_or_background_job(self, provider):
        invalid = [None, [], "implementation.py", ["implementation.py"] * 2,
                   ["../implementation.py"], [str(self.source)], ["missing.py"], [4],
                   [f"file-{index}.py" for index in range(33)]]
        for selection in invalid:
            for method in (self.consult, self.submit):
                with self.subTest(selection=selection, method=method.__name__), self.assertRaises(advisor.AdvisorError):
                    method(context_files=selection)
        self.assertFalse((self.state / "jobs").exists())
        provider.assert_not_called()
        self.launch.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_context_remains_required_with_selected_files(self, provider):
        request = {key: value for key, value in self.request.items() if key != "context"}
        with self.assertRaisesRegex(advisor.AdvisorError, "context"):
            advisor.submit_consultation(request, config_path=self.config, state_dir=self.state)
        self.assertFalse(self.state.exists())
        provider.assert_not_called()
        self.launch.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_selected_files_cannot_mix_with_other_snapshot_routes(self, provider):
        for field in ("context_snapshot_id", "file_context_id"):
            for method in (self.consult, self.submit):
                with self.subTest(field=field, method=method.__name__), self.assertRaisesRegex(advisor.AdvisorError, "cannot be combined"):
                    method(**{field: "a" * 64})
        metadata = {"com.zcode/request-context": {"session_id": "native"}}
        ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kwargs: metadata)))
        submit = advisor.build_server()._tool_manager.get_tool("consult_advisor").fn
        with patch.object(advisor, "capture_zcode_context") as capture:
            for selection in ({"context_files": ["implementation.py"]}, {"file_context_id": "a" * 64}):
                request = {key: value for key, value in self.request.items() if key != "context_files"} | selection
                with self.subTest(selection=selection), self.assertRaisesRegex(advisor.AdvisorError, "ZCode's native capture"):
                    submit(request, ctx)
            capture.assert_not_called()
        self.assertFalse(self.state.exists())
        provider.assert_not_called()
        self.launch.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_assembled_limit_includes_file_evidence_and_request_context(self, provider):
        self.source.write_text("x" * (7 * 1024 * 1024 + 512 * 1024))
        context = "y" * (768 * 1024)
        self.assertLess(len(json.dumps(self.request | {"context": context}).encode()), advisor.MAX_INPUT_BYTES)

        with self.assertRaisesRegex(advisor.AdvisorError, "8 MiB; nothing was silently truncated"):
            self.submit(context=context)

        self.assertFalse((self.state / "jobs").exists())
        provider.assert_not_called()
        self.launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
