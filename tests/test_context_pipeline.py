import hashlib
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_context_pipeline", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class ContextPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / "state"
        self.config = self.root / "absent.json"
        self.request = {"provider": "codex", "workspace": str(self.root), "host": "zcode",
                        "session_id": "native-session", "task_id": "task", "stage": "before_plan",
                        "question": "Review this", "context": "See native evidence."}
        self.database = self.root / ".zcode/cli/db/db.sqlite"
        self.database.parent.mkdir(parents=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT)")
            connection.execute("INSERT INTO session VALUES (?,?)", (self.request["session_id"], str(self.root)))
        environment = patch.dict(os.environ, {"ZCODE_SESSION_DB_PATH": str(self.database)})
        environment.start()
        self.addCleanup(environment.stop)

    def snapshot(self, extra=""):
        payload = {"schema_version": 1,
                   "binding": {key: self.request[key] for key in ("workspace", "host", "session_id")},
                   "coverage": {"semantic_model_input": "complete"}, "provenance": {"turn_id": "turn"},
                   "context": {"system": "Native system instructions", "tools": [{"name": "tool", "schema": {"type": "object"}}],
                               "messages": [{"role": "tool", "content": "Earlier result CANARY-648 " + extra}]}}
        encoded = json.dumps(payload).encode()
        snapshot_id = hashlib.sha256(encoded).hexdigest()
        directory = self.state / "contexts"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (snapshot_id + ".json")
        path.write_bytes(encoded)
        return snapshot_id, path

    @patch.object(advisor, "run_provider", return_value=("Check the canary.", "native-advisor"))
    def test_large_native_snapshot_reaches_provider_without_an_implicit_absolute_deadline(self, provider):
        snapshot_id, _ = self.snapshot("x" * advisor.MAX_INPUT_BYTES)
        result = advisor.consult(self.request | {"context_snapshot_id": snapshot_id},
                                 config_path=self.config, state_dir=self.state)
        packet = json.loads(provider.call_args.args[2].split("Context packet:\n")[1])
        self.assertEqual(packet["session_snapshot"]["context"]["tools"][0]["name"], "tool")
        self.assertIn("CANARY-648", packet["session_snapshot"]["context"]["messages"][0]["content"])
        self.assertIsNone(provider.call_args.args[5])
        self.assertEqual(provider.call_args.kwargs["idle_timeout_seconds"], 1200)
        self.assertEqual(result["context_transfer"]["snapshot_id"], snapshot_id)

    @patch.object(advisor, "run_provider")
    def test_cross_scope_and_oversized_context_fail_before_provider(self, provider):
        snapshot_id, _ = self.snapshot()
        with self.assertRaisesRegex(advisor.AdvisorError, "does not belong"):
            advisor.consult(self.request | {"session_id": "foreign", "context_snapshot_id": snapshot_id},
                             config_path=self.config, state_dir=self.state)
        with patch.object(advisor, "MAX_CONTEXT_BYTES", 10):
            with self.assertRaisesRegex(advisor.AdvisorError, "nothing was silently truncated"):
                advisor.consult(self.request | {"context_snapshot_id": snapshot_id},
                                 config_path=self.config, state_dir=self.state)
        provider.assert_not_called()

    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "run_provider")
    def test_background_job_freezes_snapshot_and_verifies_it_again_before_launch(self, provider, launch):
        self.addCleanup(advisor.WORKERS.clear)
        launch.return_value.poll.return_value = None
        snapshot_id, path = self.snapshot()
        job = advisor.submit_consultation(self.request | {"context_snapshot_id": snapshot_id},
                                          config_path=self.config, state_dir=self.state)
        directory = Path(job["advice_path"]).parent
        self.assertIsNone(json.loads((directory / "job.json").read_text())["deadline"])
        self.assertEqual(json.loads((directory / "request.json").read_text())["request"]["context_snapshot_id"], snapshot_id)
        path.write_text('{}')
        self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        self.assertIn("integrity", advisor.read_advice(job["job_id"], state_dir=self.state)["error"])
        provider.assert_not_called()

    @patch.object(advisor.subprocess, "Popen")
    def test_dependency_boundary_is_frozen_in_job_and_advisor_packet(self, launch):
        self.addCleanup(advisor.WORKERS.clear)
        launch.return_value.poll.return_value = None
        request = self.request | {"dependent_paths": [str(self.root / "dependent.py")]}
        packet, _ = advisor.context_packet(request, self.state)
        self.assertEqual(packet["dependent_paths"], request["dependent_paths"])
        job = advisor.submit_consultation(request, config_path=self.config, state_dir=self.state)
        directory = Path(job["advice_path"]).parent
        self.assertEqual(json.loads((directory / "job.json").read_text())["dependent_paths"], request["dependent_paths"])
        self.assertEqual(json.loads((directory / "request.json").read_text())["request"]["dependent_paths"], request["dependent_paths"])

    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "run_provider", return_value=("Keep the canonical session root.", "fake-advisor-session"))
    def test_nested_native_cwd_keeps_canonical_scope_through_submit_provider_and_read(self, provider, launch):
        self.addCleanup(advisor.WORKERS.clear)
        launch.return_value.poll.return_value = None
        child = self.root / "src"
        child.mkdir()
        request = {"provider": "codex", "question": "Review workspace ownership.",
                   "stage": "before_task", "dependent_paths": ["src/car.js"]}
        native = {"workspace_path": str(child), "session_id": self.request["session_id"], "turn_id": "original-turn"}
        meta = {"com.zcode/request-context": native}
        ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kwargs: meta)))
        messages = [{"role": "system", "content": "Fixture system instructions."},
                    {"role": "user", "content": "Fixture consultation task."}]
        entry = {"type": "model_io", "sessionId": native["session_id"], "turnId": native["turn_id"],
                 "querySource": "main_turn", "requestId": "request-fixture",
                 "request": {"messages": messages, "sdkMessages": messages,
                             "body": {"messages": messages, "system": "Fixture system instructions.",
                                      "tools": [{"name": "consult_advisor", "input_schema": {"type": "object"}}]}},
                 "response": {"toolCalls": [{"id": "consult-fixture", "name": "mcp__plugin_advisor_advisor__consult_advisor",
                                             "input": {"request": request}}]}}
        source = self.root / ".zcode/cli/rollout" / f"model-io-{native['session_id']}.jsonl"
        source.parent.mkdir()
        source.write_text(json.dumps(entry) + "\n")
        server = advisor.build_server()
        submit = server._tool_manager.get_tool("consult_advisor").fn
        read = server._tool_manager.get_tool("read_advice").fn
        scope = {"workspace": str(self.root), "session_id": native["session_id"], "turn_id": native["turn_id"]}
        with patch.object(Path, "home", return_value=self.root), \
                patch.dict(os.environ, {"ADVISOR_STATE_DIR": str(self.state), "ADVISOR_CONFIG": str(self.config)}), \
                patch.object(advisor, "submit_consultation", wraps=advisor.submit_consultation) as submission:
            pending = submit(request, ctx)
            prepared = submission.call_args.args[0]
            self.assertEqual(prepared["workspace"], str(self.root))
            self.assertEqual(prepared["_native_scope"], scope)
            self.assertEqual(pending["status"], "pending")
            directory = Path(pending["advice_path"]).parent
            job = json.loads((directory / "job.json").read_text())
            snapshot = json.loads((self.state / "contexts" / (prepared["context_snapshot_id"] + ".json")).read_text())
            self.assertEqual(snapshot["binding"], {"workspace": str(self.root), "host": "zcode", "session_id": native["session_id"]})
            self.assertEqual(job["scope"]["workspace"], str(self.root))
            self.assertEqual(job["native_turn_id"], "original-turn")
            dependency = next((self.state / "checkpoints/dependencies").glob("*.sqlite3"))
            with sqlite3.connect(dependency) as connection:
                self.assertEqual(connection.execute("SELECT job_id,satisfied FROM requirements").fetchall(), [(pending["job_id"], 0)])
            self.assertEqual(advisor.run_job(pending["job_id"], state_dir=self.state), 0)
            packet = json.loads(provider.call_args.args[2].split("Context packet:\n")[1])
            self.assertEqual(provider.call_args.args[3], self.root)
            self.assertEqual(packet["workspace"], str(self.root))
            self.assertEqual(packet["session_snapshot"]["binding"], snapshot["binding"])
            source.unlink()
            native["turn_id"] = "wake-turn"
            with sqlite3.connect(self.database) as connection:
                connection.execute("INSERT INTO session VALUES (?,?)", ("foreign-session", str(self.root)))
            foreign = {"com.zcode/request-context": native | {"session_id": "foreign-session"}}
            foreign_ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kwargs: foreign)))
            with self.assertRaises(advisor.AdvisorError):
                read(pending["job_id"], foreign_ctx)
            with self.assertRaises(advisor.AdvisorError):
                read("f" * 64, ctx)
            turn_database = next((self.state / "checkpoints").glob("*.sqlite3"))
            with sqlite3.connect(turn_database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT job_id FROM outstanding").fetchall(), [(pending["job_id"],)])
            result = read(pending["job_id"], ctx)
        self.assertEqual(result["job_id"], pending["job_id"])
        self.assertEqual(result["advice"], "Keep the canonical session root.")
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(list((self.state / "checkpoints").glob("*.sqlite3")), [turn_database])
        with sqlite3.connect(turn_database) as connection:
            self.assertEqual(connection.execute("SELECT job_id,status FROM reviews").fetchall(), [(pending["job_id"], "completed")])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM outstanding").fetchone()[0], 0)
        with sqlite3.connect(dependency) as connection:
            self.assertEqual(connection.execute("SELECT job_id,satisfied FROM requirements").fetchall(), [(pending["job_id"], 1)])

    @patch.object(advisor.subprocess, "Popen")
    def test_native_read_recovers_exact_attachment_after_storage_failure_without_resubmission(self, launch):
        self.addCleanup(advisor.WORKERS.clear)
        launch.return_value.poll.return_value = None
        snapshot_id, _ = self.snapshot()
        scope = {"workspace": str(self.root), "session_id": self.request["session_id"], "turn_id": "turn"}
        prepared = self.request | {"context_snapshot_id": snapshot_id, "dependent_paths": [str(self.root / "dependent.py")],
                                   "_native_scope": scope}
        meta = {"com.zcode/request-context": {**scope, "workspace_path": scope["workspace"]}}
        ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kwargs: meta)))
        server = advisor.build_server()
        submit = server._tool_manager.get_tool("consult_advisor").fn
        read = server._tool_manager.get_tool("read_advice").fn
        with patch.dict(os.environ, {"ADVISOR_STATE_DIR": str(self.state), "ADVISOR_CONFIG": str(self.config)}), \
                patch.object(advisor, "prepare_request", return_value=prepared), \
                patch.object(advisor, "attach_dependencies", side_effect=advisor.CheckpointError("injected attachment failure")):
            for _ in range(2):
                with self.assertRaisesRegex(advisor.AdvisorError, "was submitted"):
                    submit(self.request, ctx)
        directories = list((self.state / "jobs").iterdir())
        self.assertEqual(len(directories), 1)
        directory = directories[0]
        metadata = json.loads((directory / "job.json").read_text())
        self.assertEqual(metadata["dependency_attempt_id"], snapshot_id)
        self.assertEqual(launch.call_count, 1)

        dependency = next((self.state / "checkpoints/dependencies").glob("*.sqlite3"))
        with sqlite3.connect(dependency) as db:
            self.assertEqual(db.execute("SELECT job_id,satisfied FROM requirements").fetchall(), [(None, 0)])
        advisor.begin_dependencies(scope, prepared["dependent_paths"], "f" * 32, self.state)
        (directory / "result.json").write_text(json.dumps({"status": "completed", "advice": "Keep the producer until cleanup finishes."}))
        with patch.dict(os.environ, {"ADVISOR_STATE_DIR": str(self.state)}):
            (directory / "job.json").write_text(json.dumps(metadata | {"dependency_attempt_id": "f" * 32}))
            with self.assertRaisesRegex(advisor.AdvisorError, "association does not match"):
                read(metadata["job_id"], ctx)
            (directory / "job.json").write_text(json.dumps(metadata))
            result = read(metadata["job_id"], ctx)
        self.assertEqual(result["status"], "completed")
        with sqlite3.connect(dependency) as db:
            self.assertEqual(db.execute("SELECT job_id,satisfied FROM requirements WHERE attempt_id=?", (snapshot_id,)).fetchall(), [(metadata["job_id"], 1)])
            self.assertEqual(db.execute("SELECT job_id,satisfied FROM requirements WHERE attempt_id=?", ("f" * 32,)).fetchall(), [(None, 0)])
        self.assertEqual(launch.call_count, 1)

    @patch.object(advisor.subprocess, "Popen")
    def test_satisfied_native_reread_survives_alias_change_without_freshness_or_other_hold_credit(self, launch):
        self.addCleanup(advisor.WORKERS.clear)
        launch.return_value.poll.return_value = None
        original, replacement, alias = self.root / "a.py", self.root / "b.py", self.root / "link.py"
        original.write_text("original")
        replacement.write_text("replacement")
        alias.symlink_to(original)
        snapshot_id, _ = self.snapshot()
        scope = {"workspace": str(self.root), "session_id": self.request["session_id"], "turn_id": "turn"}
        paths = advisor.normalize_dependent_paths(self.root, ["link.py"])
        prepared = self.request | {"context_snapshot_id": snapshot_id, "dependent_paths": paths, "_native_scope": scope}
        meta = {"com.zcode/request-context": {**scope, "workspace_path": scope["workspace"]}}
        ctx = SimpleNamespace(request_context=SimpleNamespace(meta=SimpleNamespace(model_dump=lambda **kwargs: meta)))
        server = advisor.build_server()
        submit = server._tool_manager.get_tool("consult_advisor").fn
        read = server._tool_manager.get_tool("read_advice").fn
        with patch.dict(os.environ, {"ADVISOR_STATE_DIR": str(self.state), "ADVISOR_CONFIG": str(self.config)}), \
                patch.object(advisor, "prepare_request", return_value=prepared):
            job = submit(self.request, ctx)
            directory = Path(job["advice_path"]).parent
            (directory / "result.json").write_text(json.dumps({"status": "completed", "advice": "Saved historical advice."}))
            first = read(job["job_id"], ctx)
            event = {"cwd": str(self.root), "session_id": self.request["session_id"], "turnId": "turn",
                     "hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(original)}}
            self.assertEqual(advisor.review_checkpoint(event, self.state), {})
            self.assertEqual(advisor.review_checkpoint(event | {"hook_event_name": "Stop"}, self.state)["decision"], "block")
            turn_database = next((self.state / "checkpoints").glob("*.sqlite3"))
            with sqlite3.connect(turn_database) as db:
                receipts = db.execute("SELECT * FROM reviews").fetchall()
                work = db.execute("SELECT * FROM work").fetchall()
            advisor.begin_dependencies(scope, paths, "f" * 32, self.state)
            alias.unlink()
            alias.symlink_to(replacement)
            meta["com.zcode/request-context"]["turn_id"] = "later-turn"
            self.assertEqual(read(job["job_id"], ctx), first)
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(list((self.state / "checkpoints").glob("*.sqlite3")), [turn_database])
        with sqlite3.connect(turn_database) as db:
            self.assertEqual(db.execute("SELECT * FROM reviews").fetchall(), receipts)
            self.assertEqual(db.execute("SELECT * FROM work").fetchall(), work)
        dependency = next((self.state / "checkpoints/dependencies").glob("*.sqlite3"))
        with sqlite3.connect(dependency) as db:
            self.assertEqual(db.execute("SELECT job_id,satisfied FROM requirements WHERE attempt_id=?", (snapshot_id,)).fetchall(), [(job["job_id"], 1)])
            self.assertEqual(db.execute("SELECT job_id,satisfied FROM requirements WHERE attempt_id=?", ("f" * 32,)).fetchall(), [(None, 0)])


if __name__ == "__main__":
    unittest.main()
