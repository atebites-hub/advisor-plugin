import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "plugins/advisor/review_checkpoints.py"
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("advisor_checkpoint_tests", PATH)
checkpoints = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checkpoints
SPEC.loader.exec_module(checkpoints)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database = self.root / "native" / "index.sqlite3"
        self.database.parent.mkdir()
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT)")
            connection.execute("INSERT INTO session VALUES (?,?)", ("sess_fixture", str(self.workspace)))
        native_env = patch.dict(os.environ, {"ZCODE_SESSION_DB_PATH": str(self.database)})
        native_env.start()
        self.addCleanup(native_env.stop)
        self.state = self.root / "state"
        self.native = {"workspace_path": str(self.workspace), "session_id": "sess_fixture", "turn_id": "turn_fixture"}
        self.meta = {"com.zcode/request-context": self.native}
        self.event = {"cwd": str(self.workspace), "session_id": "sess_fixture", "turnId": "turn_fixture"}
        self.scope = {"workspace": str(self.workspace), "session_id": "sess_fixture", "turn_id": "turn_fixture"}

    def job(self, number=1, submitted=100, stage="before_task"):
        job = {"job_id": f"{number:064x}", "scope": {"workspace": str(self.workspace), "host": "zcode", "session_id": "sess_fixture", "task_id": "worker-chosen"},
               "native_turn_id": "turn_fixture", "submitted_at_ns": submitted, "stage": stage,
               "context_transfer": {"mode": "native_snapshot"}}
        directory = self.state / "jobs" / job["job_id"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(json.dumps(job))
        return job

    def retrieve(self, job, status="completed"):
        verified = checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
        checkpoints.record_review(verified, {"job_id": job["job_id"], "status": status, "advice": "Verified fixture advice."}, self.state)

    def hook(self, name="PreToolUse", tool="Write", read_status=None, watch_command=None, **changes):
        with patch.object(checkpoints.time, "time_ns", return_value=1000):
            return checkpoints.review_checkpoint(self.event | {"hook_event_name": name, "tool_name": tool} | changes, self.state,
                                                 read_status=read_status, watch_command=watch_command)

    def assertDenied(self, output):
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertTrue(output["hookSpecificOutput"]["additionalContext"])

    def test_scope_is_verified_before_native_advice_and_manual_calls_have_no_receipt(self):
        self.assertIsNone(checkpoints.verify_job_scope("not-a-job", {}, self.state))
        job = self.job()
        self.assertEqual(checkpoints.verify_job_scope(job["job_id"], self.meta, self.state), job)
        for field, value in (("session_id", "sess_other"),):
            with self.subTest(field=field), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.verify_job_scope(job["job_id"], {"com.zcode/request-context": self.native | {field: value}}, self.state)
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.verify_job_scope(job["job_id"], {"com.zcode/request-context": self.native | {"workspace_path": str(other)}}, self.state)
        for change in ({"context_transfer": {"mode": "supplied_packet"}}, {"scope": job["scope"] | {"host": "claude"}},
                       {"submitted_at_ns": True}, {"native_turn_id": None}, {"job_id": "f" * 64}):
            with self.subTest(change=change):
                (self.state / "jobs" / job["job_id"] / "job.json").write_text(json.dumps(job | change))
                with self.assertRaises(checkpoints.CheckpointError):
                    checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
        self.assertEqual(self.hook(), {})

    def test_canonical_workspace_alias_is_accepted_but_job_symlink_is_not(self):
        job = self.job()
        alias = self.root / "alias"
        alias.symlink_to(self.workspace, target_is_directory=True)
        meta = {"com.zcode/request-context": self.native | {"workspace_path": str(alias)}}
        self.assertEqual(checkpoints.verify_job_scope(job["job_id"], meta, self.state), job)
        path = self.state / "jobs" / job["job_id"] / "job.json"
        saved = self.root / "saved.json"
        path.replace(saved)
        path.symlink_to(saved)
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)

    def test_submission_allows_independent_edits_without_a_retrieval_receipt(self):
        job = self.job()
        verified = checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
        self.assertEqual(self.hook(), {})
        checkpoints.record_review(verified, {"status": "pending"}, self.state)
        self.assertEqual(self.hook(), {})
        checkpoints.register_review(verified, self.state)
        output = self.hook()
        self.assertNotIn("permissionDecision", output["hookSpecificOutput"])
        self.assertIn("only independent work", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertGreaterEqual(connection.execute("SELECT last_edit_ns FROM work").fetchone()[0], 1000)
        self.retrieve(job, "failed")
        self.assertEqual(self.hook(), {})
        self.retrieve(job)
        self.assertEqual(self.hook(), {})

    def test_only_known_file_tools_are_gated_and_other_events_do_not_create_state(self):
        for tool in ("Read", "Glob", "Grep", "Bash", "js", "Agent", "mcp__other__write"):
            with self.subTest(tool=tool):
                self.assertEqual(self.hook(tool=tool), {})
        self.assertEqual(self.hook(name="SessionStart"), {})
        self.assertFalse(self.state.exists())
        self.assertEqual(self.hook(name="PostToolUse"), {})
        self.assertDenied(self.hook(tool=[]))
        self.assertDenied(self.hook(session_id=None))
        for tool in ("Write", "Edit", "ApplyPatch", "MultiEdit", "NotebookEdit"):
            with self.subTest(tool=tool):
                self.assertEqual(self.hook(tool=tool), {})

    def test_admitted_edit_is_dirty_even_without_success_and_rereading_old_advice_is_stale(self):
        early = self.job()
        self.retrieve(early)
        self.assertEqual(self.hook(name="Stop"), {})
        self.assertEqual(self.hook(), {})
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        self.retrieve(early)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        final = self.job(number=2, submitted=2000, stage="during_task")
        checkpoints.verify_job_scope(final["job_id"], self.meta, self.state)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        self.retrieve(final)
        self.assertEqual(self.hook(name="Stop"), {})
        self.assertEqual(self.hook(tool="Edit"), {})
        self.assertEqual(self.hook(name="Stop")["decision"], "block")

    def test_short_during_task_review_does_not_require_another_review(self):
        self.retrieve(self.job(stage="during_task"))
        self.assertEqual(self.hook(), {})
        self.assertEqual(self.hook(name="Stop"), {})

    def test_registered_ready_jobs_repeat_alerts_until_actual_terminal_retrieval(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        calls = []

        def finished(job_id):
            calls.append(job_id)
            return {"job_id": job_id, "status": "completed", "advice": "private-advice-canary"}

        for event in ("PostToolUse", "PostToolUseFailure", "PostToolUse"):
            output = self.hook(name=event, tool="Read", read_status=finished)
            text = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn(job["job_id"], text)
            self.assertIn("read_advice", text)
            self.assertNotIn("private-advice-canary", text)
        self.assertEqual(calls, [job["job_id"]] * 3)
        self.assertEqual(self.hook(name="Stop", read_status=finished)["decision"], "block")
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM outstanding").fetchone()[0], 1)
        checkpoints.record_review(job, {"status": "pending"}, self.state)
        self.assertTrue(self.hook(name="PostToolUse", read_status=finished))
        self.retrieve(job)
        self.assertEqual(self.hook(name="PostToolUse", read_status=finished), {})
        self.assertEqual(self.hook(name="Stop"), {})
        checkpoints.register_review(job, self.state)
        self.assertEqual(self.hook(name="PostToolUse", read_status=finished), {})

    def test_pending_observation_does_not_fake_completion_or_clear_submission(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        self.assertEqual(self.hook(name="PostToolUse"), {})
        self.assertEqual(self.hook(name="PostToolUse", read_status=lambda _: {"status": "pending"}), {})
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        self.assertEqual(self.hook(name="Stop", read_status=lambda _: {"status": "pending"})["decision"], "block")

    def test_failed_or_interrupted_submissions_alert_then_report_incomplete_without_retry(self):
        for number, status in enumerate(("failed", "interrupted"), start=1):
            with self.subTest(status=status):
                job = self.job(number=number)
                checkpoints.register_review(job, self.state)
                self.assertIn(job["job_id"], str(self.hook(name="PostToolUse", read_status=lambda _: {"status": status})))
                self.assertEqual(self.hook(name="Stop", read_status=lambda _: {"status": status})["decision"], "block")
                self.retrieve(job, status)
                text = self.hook(name="Stop")["systemMessage"]
                self.assertIn("incomplete", text)
                self.assertIn("do not retry", text)
                checkpoints.register_review(job, self.state)
                self.assertEqual(self.hook(name="PostToolUse"), {})

    def test_early_failure_followed_by_independent_edit_keeps_planning_intent(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        self.assertIn("independent", str(self.hook()))
        self.retrieve(job, "failed")
        output = self.hook(name="Stop")
        self.assertIn("early Advisor review failed", output["systemMessage"])
        self.assertIn("incomplete", output["systemMessage"])

    def test_registration_metadata_is_immutable_and_duplicate_safe(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        checkpoints.register_review(job, self.state)
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM outstanding").fetchone()[0], 1)
        for changed in (job | {"submitted_at_ns": 200}, job | {"stage": "during_task"}):
            with self.subTest(changed=changed), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.register_review(changed, self.state)
            with self.assertRaises(checkpoints.CheckpointError):
                checkpoints.record_review(changed, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.retrieve(job)
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.register_review(job | {"submitted_at_ns": 200}, self.state)

    def test_job_notifications_are_scoped_before_observation(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        with patch.object(checkpoints, "_outstanding", wraps=checkpoints._outstanding):
            for changes in ({"turnId": "other"}, {"session_id": "other"}):
                with self.subTest(changes=changes):
                    read = unittest.mock.Mock(return_value={"status": "completed", "advice": "Verified fixture advice."})
                    self.assertEqual(self.hook(name="PostToolUse", read_status=read, **changes), {})
                    read.assert_not_called()
        observer = unittest.mock.Mock(return_value={"status": "completed", "advice": "Verified fixture advice."})
        self.assertTrue(self.hook(name="PostToolUse", read_status=observer))
        observer.assert_called_once_with(job["job_id"])

    def test_status_errors_never_clear_outstanding_or_make_receipts(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        invalid = (None, {}, {"status": "ready"}, {"status": "completed", "job_id": "f" * 64})
        for result in invalid:
            with self.subTest(result=result):
                output = self.hook(name="PostToolUse", read_status=lambda _: result)
                self.assertIn("could not be verified", output["hookSpecificOutput"]["additionalContext"])
                self.assertIn("read_advice", str(output))
        output = self.hook(name="Stop", read_status=unittest.mock.Mock(side_effect=ValueError("corrupt")))
        self.assertIn("could not be verified", output["systemMessage"])
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM outstanding").fetchone()[0], 1)

    def test_independent_edit_after_final_submission_keeps_its_advice_stale(self):
        early = self.job()
        checkpoints.register_review(early, self.state)
        self.hook()
        self.retrieve(early)
        final = self.job(number=2, submitted=2000, stage="during_task")
        checkpoints.register_review(final, self.state)
        self.hook(tool="Edit")
        self.retrieve(final)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")

    def test_new_turn_retrieval_records_only_original_turn_and_cannot_satisfy_new_final_review(self):
        old = self.job()
        checkpoints.register_review(old, self.state)
        new_meta = {"com.zcode/request-context": self.native | {"turn_id": "turn_new"}}
        verified = checkpoints.verify_job_scope(old["job_id"], new_meta, self.state)
        self.assertEqual(verified["native_turn_id"], "turn_fixture")
        checkpoints.record_review(verified, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.assertEqual(len(list((self.state / "checkpoints").glob("*.sqlite3"))), 1)
        self.assertEqual(self.hook(turnId="turn_new"), {})
        current = self.job(number=2, submitted=100, stage="before_plan") | {"native_turn_id": "turn_new"}
        checkpoints.register_review(current, self.state)
        checkpoints.record_review(current, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.hook(tool="Edit", turnId="turn_new")
        checkpoints.record_review(verified, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.assertEqual(self.hook(name="Stop", turnId="turn_new")["decision"], "block")

    def test_only_verified_native_background_watcher_allows_pending_stop_to_yield(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        command = lambda job_id: "advisor wait " + job_id
        inputs = {"command": command(job["job_id"]), "run_in_background": True}
        response = {"status": "backgrounded", "interrupted": False, "backgroundTaskId": "background-1"}
        invalid = [
            {"tool_name": "Read"},
            {"hook_event_name": "PostToolUseFailure"},
            {"tool_input": inputs | {"run_in_background": 1}},
            {"tool_input": inputs | {"command": "advisor wait " + "f" * 64}},
            {"tool_response": response | {"status": "completed", "advice": "Verified fixture advice."}},
            {"tool_response": response | {"interrupted": True}},
            {"tool_response": response | {"backgroundTaskId": ""}},
            {"tool_response": response | {"backgroundTaskId": 1}},
        ]
        event = self.event | {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": inputs, "tool_response": response}
        for changes in invalid:
            with self.subTest(changes=changes):
                checkpoints.review_checkpoint(event | changes, self.state, watch_command=command)
                self.assertEqual(self.hook(name="Stop")["decision"], "block")
        checkpoints.review_checkpoint(event, self.state, watch_command=command)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        output = self.hook(name="Stop", read_status=lambda _: {"status": "pending"})
        self.assertNotIn("decision", output)
        self.assertIn("waiting and remains incomplete", output["systemMessage"])
        self.assertIn("read_advice", output["systemMessage"])
        self.assertEqual(self.hook(name="Stop", read_status=lambda _: {"status": "completed", "advice": "Verified fixture advice."})["decision"], "block")
        self.retrieve(job)
        self.assertEqual(self.hook(name="Stop"), {})

    def test_all_pending_jobs_need_verified_watchers_and_aliases_are_supported(self):
        first, second = self.job(), self.job(number=2)
        for job in (first, second):
            checkpoints.register_review(job, self.state)
        command = lambda job_id: "advisor wait " + job_id
        for job in (first, second):
            event = self.event | {"hook_event_name": "PostToolUse", "toolName": "Bash",
                    "toolInput": {"command": command(job["job_id"]), "run_in_background": True},
                    "toolResponse": {"status": "backgrounded", "interrupted": False, "backgroundTaskId": job["job_id"]}}
            checkpoints.review_checkpoint(event, self.state, watch_command=command)
            if job == first:
                self.assertEqual(self.hook(name="Stop")["decision"], "block")
        self.assertIn("waiting and remains incomplete", self.hook(name="Stop", read_status=lambda _: {"status": "pending"})["systemMessage"])
        with patch("subprocess.Popen") as provider:
            self.assertTrue(self.hook(name="PostToolUse", read_status=lambda _: {"status": "failed"}))
            provider.assert_not_called()

    def test_registration_and_notification_survive_process_restart_without_a_receipt(self):
        job = self.job()
        checkpoints.register_review(job, self.state)
        code = "import json,runpy,sys; from pathlib import Path; m=runpy.run_path(sys.argv[1]); print(json.dumps(m['review_checkpoint'](json.loads(sys.argv[3]),Path(sys.argv[2]),read_status=lambda jid:{'job_id':jid,'status':'completed'})))"
        event = self.event | {"hook_event_name": "PostToolUse", "tool_name": "Read"}
        output = subprocess.run([sys.executable, "-c", code, str(PATH), str(self.state), json.dumps(event)], check=True, capture_output=True, text=True)
        self.assertIn(job["job_id"], output.stdout)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        self.retrieve(job)
        self.assertEqual(self.hook(name="PostToolUse", read_status=lambda _: {"status": "completed", "advice": "Verified fixture advice."}), {})

    def test_fresh_failed_final_review_allows_an_explicit_incomplete_report(self):
        self.retrieve(self.job())
        self.assertEqual(self.hook(), {})
        for number, status in enumerate(("failed", "interrupted"), start=2):
            with self.subTest(status=status):
                self.retrieve(self.job(number=number, submitted=2000 + number, stage="during_task"), status)
                output = self.hook(name="Stop", stop_hook_active=True)
                self.assertNotIn("decision", output)
                self.assertIn("incomplete", output["systemMessage"])
                self.assertIn("do not retry", output["systemMessage"])

    def test_unavailable_capture_before_advice_gives_no_review_credit_but_allows_independent_edits(self):
        with patch("subprocess.Popen") as provider:
            checkpoints.record_unavailable_review(self.scope, 2000, self.state)
            self.assertEqual(self.hook(), {})
            self.assertEqual(self.hook(name="Stop"), {})
            provider.assert_not_called()
        self.assertFalse((self.state / "jobs").exists())
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM unavailable").fetchone()[0], 0)

    def test_unavailable_final_capture_allows_only_a_truthful_incomplete_stop(self):
        self.retrieve(self.job())
        self.assertEqual(self.hook(), {})
        jobs = set((self.state / "jobs").iterdir())
        with patch("subprocess.Popen") as provider:
            checkpoints.record_unavailable_review(self.scope, 2000, self.state)
            output = self.hook(name="Stop")
            provider.assert_not_called()
        self.assertNotIn("decision", output)
        for phrase in ("review is incomplete", "No Advisor job or provider was started", "do not retry",
                       "CLI directly", "older advice", "fall back to another provider"):
            self.assertIn(phrase, output["systemMessage"])
        self.assertEqual(set((self.state / "jobs").iterdir()), jobs)
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT status FROM reviews").fetchall(), [("completed",)])
            self.assertEqual(connection.execute("SELECT started_at_ns, last_edit_ns FROM unavailable").fetchall(), [(2000, 1000)])

    def test_unavailable_attempt_must_begin_after_current_dirty_revision(self):
        self.retrieve(self.job())
        self.assertEqual(self.hook(), {})
        for started in (999, 1000):
            with self.subTest(started=started):
                checkpoints.record_unavailable_review(self.scope, started, self.state)
                self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with patch.object(checkpoints.time, "time_ns", return_value=3000):
            self.assertEqual(checkpoints.review_checkpoint(self.event | {"hook_event_name": "PreToolUse", "tool_name": "Edit"}, self.state), {})
        checkpoints.record_unavailable_review(self.scope, 2000, self.state)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM unavailable").fetchone()[0], 0)

    def test_later_edit_invalidates_marker_and_older_attempt_cannot_replace_latest(self):
        self.retrieve(self.job())
        self.assertEqual(self.hook(), {})
        checkpoints.record_unavailable_review(self.scope, 2000, self.state)
        checkpoints.record_unavailable_review(self.scope, 1500, self.state)
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT started_at_ns FROM unavailable").fetchone()[0], 2000)
        self.assertNotIn("decision", self.hook(name="Stop"))
        self.assertEqual(self.hook(tool="Edit"), {})
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with sqlite3.connect(next((self.state / "checkpoints").glob("*.sqlite3"))) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM unavailable").fetchone()[0], 0)

    def test_fresh_review_results_keep_precedence_over_unavailable_marker(self):
        early = self.job()
        final = self.job(number=2, submitted=3000, stage="during_task")
        for status in ("completed", "failed", "interrupted"):
            with self.subTest(status=status):
                state = self.state / status
                checkpoints.record_review(early, {"status": "completed", "advice": "Verified fixture advice."}, state)
                with patch.object(checkpoints.time, "time_ns", return_value=1000):
                    self.assertEqual(checkpoints.review_checkpoint(self.event | {"hook_event_name": "PreToolUse", "tool_name": "Edit"}, state), {})
                checkpoints.record_unavailable_review(self.scope, 2000, state)
                checkpoints.record_review(final, {"status": status, "advice": "Verified fixture advice."}, state)
                output = checkpoints.review_checkpoint(self.event | {"hook_event_name": "Stop"}, state)
                if status == "completed":
                    self.assertEqual(output, {})
                else:
                    self.assertIn("review failed or was interrupted", output["systemMessage"])
                    self.assertNotIn("No Advisor job", output["systemMessage"])

    def test_unavailable_markers_are_isolated_and_reads_do_not_create_them(self):
        self.retrieve(self.job())
        self.assertEqual(self.hook(), {})
        other = self.root / "other"
        other.mkdir()
        for changes in ({"workspace": str(other)}, {"session_id": "sess_other"}, {"turn_id": "turn_other"}):
            with self.subTest(changes=changes):
                checkpoints.record_unavailable_review(self.scope | changes, 2000, self.state)
                self.assertEqual(self.hook(name="Stop")["decision"], "block")
        pending = self.job(number=2, submitted=2000, stage="during_task")
        verified = checkpoints.verify_job_scope(pending["job_id"], self.meta, self.state)
        self.assertIsNone(checkpoints.verify_job_scope(pending["job_id"], {}, self.state))
        checkpoints.record_review(verified, {"status": "pending"}, self.state)
        self.assertEqual(self.hook(tool="Read"), {})
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        for database in (self.state / "checkpoints").glob("*.sqlite3"):
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM unavailable").fetchone()[0], 0)

    def test_unavailable_attempt_rejects_invalid_scope_and_timestamp(self):
        invalid = [None, [], {}, self.scope | {"workspace": "relative"},
                   self.scope | {"workspace": str(self.root / "missing")},
                   self.scope | {"session_id": None}, self.scope | {"turn_id": "bad\x00turn"}]
        for scope in invalid:
            with self.subTest(scope=scope), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.record_unavailable_review(scope, 2000, self.state)
        for started in (None, True, 0, -1, 1.5, "2000"):
            with self.subTest(started=started), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.record_unavailable_review(self.scope, started, self.state)
        self.assertFalse(self.state.exists())

    def test_receipts_are_isolated_by_native_turn_session_and_workspace(self):
        self.retrieve(self.job())
        for changes in ({"turnId": "turn_other"}, {"session_id": "sess_other"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.hook(**changes), {})
        other = self.root / "other"
        other.mkdir()
        self.assertEqual(self.hook(cwd=str(other)), {})
        self.assertDenied(self.hook(sessionId="conflicting_session"))
        self.assertEqual(self.hook(name="Stop", turnId="turn_other"), {})

    def test_saved_job_time_cannot_be_rewritten_to_make_old_review_fresh(self):
        early = self.job()
        self.retrieve(early)
        self.assertEqual(self.hook(), {})
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.record_review(early | {"submitted_at_ns": 3000}, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.assertEqual(self.hook(name="Stop")["decision"], "block")
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.record_review(early, {"job_id": "e" * 64, "status": "completed"}, self.state)

    def test_corrupt_or_unavailable_state_denies_edits_and_reports_incomplete_stop(self):
        job = self.job()
        self.retrieve(job)
        database = next((self.state / "checkpoints").glob("*.sqlite3"))
        database.write_bytes(b"not a sqlite database")
        self.assertDenied(self.hook())
        self.assertNotIn("decision", self.hook(name="Stop"))
        self.assertIn("could not be verified", self.hook(name="Stop")["systemMessage"])
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.record_review(job, {"status": "completed", "advice": "Verified fixture advice."}, self.state)
        self.assertEqual(self.hook(tool="Read"), {})
        unavailable = self.root / "state-file"
        unavailable.write_text("file")
        self.assertDenied(checkpoints.review_checkpoint(self.event | {"hook_event_name": "PreToolUse", "tool_name": "Edit"}, unavailable))

    def test_concurrent_processes_preserve_all_receipts_in_private_state(self):
        jobs = [self.job(number=number, submitted=number) for number in range(1, 5)]
        code = "import json,runpy,sys; from pathlib import Path; module=runpy.run_path(sys.argv[1]); module['record_review'](json.loads(sys.argv[3]), {'status':'completed','advice':'Verified fixture advice.'}, Path(sys.argv[2]))"
        processes = [subprocess.Popen([sys.executable, "-c", code, str(PATH), str(self.state), json.dumps(job)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for job in jobs]
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, (stdout, stderr))
        database = next((self.state / "checkpoints").glob("*.sqlite3"))
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], len(jobs))
        self.assertEqual(self.hook(), {})
        if os.name != "nt":
            self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            self.assertEqual(database.parent.stat().st_mode & 0o777, 0o700)


class DependencyTests(unittest.TestCase):
    job = CheckpointTests.job
    hook = CheckpointTests.hook
    assertDenied = CheckpointTests.assertDenied

    def setUp(self):
        CheckpointTests.setUp(self)
        (self.workspace / "src").mkdir()
        self.target = self.workspace / "src" / "car.js"
        self.target.write_text("original")
        self.attempt = "a" * 32

    def begin(self, paths=None, attempt=None):
        return checkpoints.begin_dependencies(self.scope, ["src/car.js"] if paths is None else paths,
                                              attempt or self.attempt, self.state)

    def attach(self, job=None, paths=None, attempt=None):
        job = job or self.job(stage="during_task")
        job["dependent_paths"] = ["src/car.js"] if paths is None else paths
        (self.state / "jobs" / job["job_id"] / "job.json").write_text(json.dumps(job))
        checkpoints.attach_dependencies(self.scope, attempt or self.attempt, job, self.state)
        return job

    def edit(self, path=None, tool="Edit", **changes):
        return self.hook(tool=tool, tool_input={"file_path": str(path or self.target)}, **changes)

    def test_requirement_is_armed_before_a_job_and_only_declared_paths_are_blocked(self):
        self.begin()
        self.assertDenied(self.edit())
        self.assertNotIn("permissionDecision", str(self.edit(self.workspace / "README.md")))
        self.assertFalse((self.state / "jobs").exists())
        self.assertEqual(self.target.read_text(), "original")

    def test_pending_failure_and_unavailable_never_release_but_completed_read_does(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        for status in ("pending", "failed", "interrupted"):
            checkpoints.record_review(job, {"job_id": job["job_id"], "status": status, "advice": "Verified fixture advice."}, self.state)
            self.assertDenied(self.edit())
        checkpoints.record_unavailable_review(self.scope, 2000, self.state)
        self.assertDenied(self.edit())
        self.assertDenied(self.edit(read_status=lambda _: {"status": "completed", "advice": "not retrieved"}))
        for advice in (None, "", " \n"):
            with self.subTest(advice=advice), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.record_review(job, {"job_id": job["job_id"], "status": "completed", "advice": advice}, self.state)
            self.assertDenied(self.edit())
        checkpoints.record_review(job, {"job_id": job["job_id"], "status": "completed", "advice": "Use the bounded implementation."}, self.state)
        self.assertNotIn("permissionDecision", str(self.edit()))

    def test_new_turn_and_changed_cwd_cannot_bypass_same_session_requirement(self):
        self.begin()
        self.assertDenied(self.edit(turnId="turn_wake", cwd=str(self.workspace / "src")))
        self.assertDenied(self.edit(turnId="turn_wake", cwd=str(self.root)))
        self.assertEqual(self.edit(session_id="sess_other"), {})
        self.assertDenied(self.hook(name="PreToolUse", tool="Edit", cwd=str(self.workspace / "src"),
                                    tool_input={"file_path": "car.js"}))

    def test_empty_read_only_declaration_and_invalid_paths(self):
        self.begin([])
        self.assertEqual(self.edit(), {})
        for paths in (None, "src/car.js", [""], ["../escape"], ["src/*"], [1], ["bad\x00path"]):
            with self.subTest(paths=paths), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.begin_dependencies(self.scope, paths, "b" * 32, self.state)

    def test_all_named_mutation_forms_and_patch_move_endpoints_are_guarded(self):
        self.begin()
        for tool in ("Write", "Edit", "MultiEdit"):
            with self.subTest(tool=tool):
                self.assertDenied(self.edit(tool=tool))
        self.assertDenied(self.hook(tool="NotebookEdit", tool_input={"notebook_path": str(self.target)}))
        sections = (
            "*** Add File: src/car.js\n+new",
            "*** Update File: src/car.js\n@@\n-original\n+new",
            "*** Delete File: src/car.js",
            "*** Update File: src/car.js\n*** Move to: moved.js\n@@\n-original\n+new",
            "*** Update File: other.js\n*** Move to: src/car.js\n@@\n-old\n+new",
        )
        for section in sections:
            with self.subTest(section=section):
                self.assertDenied(self.hook(tool="ApplyPatch", tool_input={"patch_text": "*** Begin Patch\n" + section + "\n*** End Patch"}))
        independent = "*** Begin Patch\n*** Add File: README.md\n+independent\n*** End Patch"
        self.assertNotIn("permissionDecision", str(self.hook(tool="ApplyPatch", tool_input={"patch_text": independent})))
        for tool in ("Write", "Edit", "MultiEdit", "NotebookEdit", "ApplyPatch"):
            for inputs in (None, {}, {"file_path": "../outside"}, {"file_path": 3}):
                with self.subTest(tool=tool, inputs=inputs):
                    self.assertDenied(self.hook(tool=tool, tool_input=inputs))

    def test_directory_ancestry_canonical_alias_and_symlink_escape(self):
        self.begin(["src"])
        self.assertDenied(self.edit())
        self.assertDenied(self.edit(self.workspace / "src"))
        self.assertDenied(self.edit(self.workspace))
        alias = self.workspace / "linked.js"
        alias.symlink_to(self.target)
        self.assertDenied(self.edit(alias))
        self.assertNotIn("permissionDecision", str(self.edit(self.workspace / "src-other.js")))
        escape = self.workspace / "escape"
        escape.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(checkpoints.CheckpointError):
            self.begin(["escape/outside"], "b" * 32)
        self.assertDenied(self.edit(escape / "outside"))

    def test_exact_job_release_isolated_from_other_attempt_and_original_receipt_only(self):
        self.begin()
        first = self.attach()
        other_path = "src/other.js"
        self.begin([other_path], "b" * 32)
        second = self.attach(self.job(number=2), [other_path], "b" * 32)
        later = {"com.zcode/request-context": self.native | {"turn_id": "turn_later"}}
        verified = checkpoints.verify_job_scope(first["job_id"], later, self.state)
        checkpoints.record_review(verified, {"job_id": first["job_id"], "status": "completed", "advice": "Read this advice."}, self.state)
        self.assertNotIn("permissionDecision", str(self.edit(turnId="turn_later")))
        self.assertDenied(self.edit(self.workspace / other_path, turnId="turn_later"))
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_later"), self.state) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
        checkpoints.record_review(second, {"job_id": second["job_id"], "status": "failed"}, self.state)
        self.assertDenied(self.edit(self.workspace / other_path))

    def test_nested_cwd_read_keeps_original_turn_and_releases_only_its_own_hold(self):
        self.begin()
        first = self.attach()
        checkpoints.register_review(first, self.state)
        self.begin(["src/other.js"], "b" * 32)
        second = self.attach(self.job(number=2), ["src/other.js"], "b" * 32)
        checkpoints.register_review(second, self.state)
        self.assertDenied(self.edit(cwd=str(self.workspace / "src"), turnId="turn_wake"))
        later = {"com.zcode/request-context": self.native | {
            "workspace_path": str(self.workspace / "src"), "turn_id": "turn_wake"}}
        verified = checkpoints.verify_job_scope(first["job_id"], later, self.state)
        self.assertEqual(verified["scope"]["workspace"], str(self.workspace))
        self.assertEqual(verified["native_turn_id"], "turn_fixture")
        checkpoints.record_review(verified, {"job_id": first["job_id"], "status": "completed",
                                            "advice": "Read the original fixture advice."}, self.state)
        edit = {"cwd": str(self.workspace / "src"), "turnId": "turn_wake"}
        self.assertNotIn("permissionDecision", str(self.hook(tool="Edit", tool_input={"file_path": "car.js"}, **edit)))
        self.assertDenied(self.hook(tool="Edit", tool_input={"file_path": "other.js"}, **edit))
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_fixture"), self.state) as connection:
            self.assertEqual(connection.execute("SELECT job_id,status FROM reviews").fetchall(), [(first["job_id"], "completed")])
            self.assertEqual(connection.execute("SELECT job_id FROM outstanding").fetchall(), [(second["job_id"],)])
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_wake"), self.state) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_fixture"), self.state, dependencies=True) as connection:
            self.assertEqual(dict(connection.execute("SELECT job_id,satisfied FROM requirements")),
                             {first["job_id"]: 1, second["job_id"]: 0})
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT directory FROM session WHERE id='sess_fixture'").fetchone(),
                             (str(self.workspace),))

    def assertUnreadHold(self, job):
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_fixture"), self.state) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT job_id FROM outstanding").fetchall(), [(job["job_id"],)])
        with checkpoints._transaction((str(self.workspace.resolve()), "sess_fixture", "turn_fixture"), self.state, dependencies=True) as connection:
            self.assertEqual(connection.execute("SELECT job_id,satisfied FROM requirements").fetchall(), [(job["job_id"], 0)])

    def test_read_rejects_indexed_foreign_session_outside_cwd_and_symlink_escape(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        other = self.root / "other"
        other.mkdir()
        escape = self.workspace / "escape"
        escape.symlink_to(other, target_is_directory=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute("INSERT INTO session VALUES (?,?)", ("sess_other", str(self.workspace)))
        changes = ({"session_id": "sess_other"}, {"workspace_path": str(other)},
                   {"workspace_path": str(self.root)}, {"workspace_path": str(escape)})
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(checkpoints.CheckpointError):
                    checkpoints.verify_job_scope(job["job_id"], {"com.zcode/request-context": self.native | change}, self.state)
                self.assertUnreadHold(job)

    def test_read_requires_index_root_to_match_job_root_including_ancestor_changes(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        other = self.root / "other"
        other.mkdir()
        for root in (other, self.root, self.workspace / "src"):
            with self.subTest(root=root):
                with sqlite3.connect(self.database) as connection:
                    connection.execute("UPDATE session SET directory=? WHERE id='sess_fixture'", (str(root),))
                with self.assertRaises(checkpoints.CheckpointError):
                    checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
                self.assertUnreadHold(job)

    def test_read_requires_existing_native_session_row_without_creating_receipt(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        with sqlite3.connect(self.database) as connection:
            connection.execute("DELETE FROM session WHERE id='sess_fixture'")
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
        self.assertUnreadHold(job)

    def test_read_requires_existing_native_index_without_recreating_it_or_receipt(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        self.database.unlink()
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.verify_job_scope(job["job_id"], self.meta, self.state)
        self.assertFalse(self.database.exists())
        self.assertUnreadHold(job)

    def test_missing_result_identity_and_empty_advice_create_no_completed_receipt(self):
        self.begin()
        job = self.attach()
        for result in ({"status": "completed", "advice": "Advice without job identity."},
                       {"job_id": "f" * 64, "status": "completed", "advice": "Wrong job."},
                       {"job_id": job["job_id"], "status": "completed", "advice": ""}):
            with self.subTest(result=result), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.record_review(job, result, self.state)
            self.assertDenied(self.edit())
        databases = list((self.state / "checkpoints").glob("*.sqlite3"))
        self.assertEqual(databases, [])

    def test_declaration_and_attachment_are_immutable_and_workspace_bound(self):
        self.begin()
        self.begin()
        with self.assertRaises(checkpoints.CheckpointError):
            self.begin(["README.md"])
        job = self.attach()
        checkpoints.attach_dependencies(self.scope, self.attempt, job, self.state)
        for changed in (job | {"dependent_paths": ["README.md"]},
                        job | {"job_id": "f" * 64},
                        job | {"native_turn_id": "other-turn"}):
            with self.subTest(changed=changed), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.attach_dependencies(self.scope, self.attempt, changed, self.state)
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.begin_dependencies(self.scope | {"workspace": str(other)}, ["car.js"], "b" * 32, self.state)
        self.assertDenied(self.edit())

    def test_unattached_capture_failure_survives_process_restart_and_has_private_state(self):
        self.begin()
        event = self.event | {"hook_event_name": "PreToolUse", "tool_name": "Write",
                              "tool_input": {"file_path": str(self.target)}}
        code = "import json,runpy,sys;from pathlib import Path;m=runpy.run_path(sys.argv[1]);print(json.dumps(m['review_checkpoint'](json.loads(sys.argv[3]),Path(sys.argv[2]))))"
        result = subprocess.run([sys.executable, "-c", code, str(PATH), str(self.state), json.dumps(event)],
                                check=True, capture_output=True, text=True)
        self.assertDenied(json.loads(result.stdout))
        self.assertFalse((self.state / "jobs").exists())
        database = next((self.state / "checkpoints" / "dependencies").glob("*.sqlite3"))
        self.assertEqual(database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(database.parent.stat().st_mode & 0o777, 0o700)
        database.write_bytes(b"corrupt")
        self.assertDenied(self.edit())

    def test_notifications_and_waiter_observation_do_not_release_dependencies(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        finished = lambda _: {"status": "completed", "job_id": job["job_id"], "advice": "Not yet retrieved."}
        for event in ("PostToolUse", "PostToolUseFailure", "Stop"):
            with self.subTest(event=event):
                self.hook(name=event, tool="Read", read_status=finished)
                self.assertDenied(self.edit())

    def test_broken_symlink_cannot_hide_the_session_dependency_state(self):
        self.begin()
        database = next((self.state / "checkpoints" / "dependencies").glob("*.sqlite3"))
        original = database.read_bytes()
        database.unlink()
        database.symlink_to(self.root / "missing")
        self.assertDenied(self.edit())
        database.unlink()
        database.write_bytes(original)
        directory = database.parent
        saved = directory.with_name("saved-dependencies")
        directory.rename(saved)
        directory.symlink_to(self.root / "missing-directory", target_is_directory=True)
        self.assertDenied(self.edit())

    def test_release_and_review_receipt_commit_together_or_neither_commits(self):
        self.begin()
        job = self.attach()
        checkpoints.register_review(job, self.state)
        database = next((self.state / "checkpoints" / "dependencies").glob("*.sqlite3"))
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TRIGGER reject_release BEFORE UPDATE ON requirements BEGIN SELECT RAISE(ABORT,'blocked release'); END")
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.record_review(job, {"job_id": job["job_id"], "status": "completed", "advice": "Usable advice."}, self.state)
        turn_database = next((self.state / "checkpoints").glob("*.sqlite3"))
        with sqlite3.connect(turn_database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM outstanding").fetchone()[0], 1)
        self.assertDenied(self.edit())

    def test_begin_storage_failure_is_checkpoint_error_before_any_job(self):
        for error in (OSError("cannot create state"), sqlite3.OperationalError("database is locked")):
            with self.subTest(error=error), patch.object(checkpoints, "_transaction", side_effect=error):
                with self.assertRaises(checkpoints.CheckpointError) as raised:
                    self.begin()
                self.assertIs(raised.exception.__cause__, error)
        self.assertFalse((self.state / "jobs").exists())

    def test_attachment_storage_failure_is_checkpoint_error_and_keeps_armed_guard(self):
        self.begin()
        job = self.job(stage="during_task") | {"dependent_paths": ["src/car.js"]}
        for error in (OSError("cannot open state"), sqlite3.OperationalError("database is locked")):
            with self.subTest(error=error), patch.object(checkpoints, "_transaction", side_effect=error):
                with self.assertRaises(checkpoints.CheckpointError) as raised:
                    checkpoints.attach_dependencies(self.scope, self.attempt, job, self.state)
                self.assertIs(raised.exception.__cause__, error)
            self.assertDenied(self.edit())

    def test_unsatisfied_requirement_precedes_an_older_fresh_completed_review_at_stop(self):
        for outcome in ("no_job", "failed", "interrupted"):
            with self.subTest(outcome=outcome), patch.object(self, "state", self.state / outcome):
                early = self.job()
                checkpoints.record_review(early, {"job_id": early["job_id"], "status": "completed",
                                                  "advice": "Earlier completed review."}, self.state)
                self.begin()
                if outcome != "no_job":
                    later = self.attach(self.job(number=2, submitted=200, stage="during_task"))
                    checkpoints.register_review(later, self.state)
                    checkpoints.record_review(later, {"job_id": later["job_id"], "status": outcome}, self.state)
                output = self.hook(name="Stop")
                self.assertIn("incomplete", output["systemMessage"])
                self.assertIn("still required", output["systemMessage"])
                self.assertDenied(self.edit())
                database = next((self.state / "checkpoints" / "dependencies").glob("*.sqlite3"))
                with sqlite3.connect(database) as connection:
                    self.assertEqual(connection.execute("SELECT satisfied FROM requirements").fetchall(), [(0,)])

    def test_literal_dynamic_route_paths_and_independent_literal_targets_work(self):
        route = self.workspace / "app" / "[id]" / "page.tsx"
        route.parent.mkdir(parents=True)
        route.write_text("original route")
        self.begin(["app/[id]/page.tsx"])
        self.assertDenied(self.edit(route))
        for independent in ("app/[slug]/page.tsx", "notes?.txt", "notes*.txt"):
            with self.subTest(independent=independent):
                self.assertNotIn("permissionDecision", str(self.edit(self.workspace / independent)))
        job = self.attach(paths=["app/[id]/page.tsx"])
        checkpoints.record_review(job, {"job_id": job["job_id"], "status": "completed", "advice": "Reviewed the route."}, self.state)
        self.assertNotIn("permissionDecision", str(self.edit(route)))

    def test_symlink_loop_declaration_returns_checkpoint_error(self):
        loop = self.workspace / "loop"
        loop.symlink_to(loop)
        with self.assertRaises(checkpoints.CheckpointError):
            self.begin(["loop/file.py"])

    def test_real_hook_symlink_loop_returns_json_denial_without_traceback(self):
        loop = self.workspace / "loop"
        loop.symlink_to(loop)
        self.begin()
        event = self.event | {"hook_event_name": "PreToolUse", "tool_name": "Edit",
                              "tool_input": {"file_path": str(loop / "file.py")}}
        runtime = PATH.with_name("advisor.py")
        environment = {**os.environ, "ADVISOR_STATE_DIR": str(self.state)}
        result = subprocess.run([sys.executable, str(runtime), "review-checkpoint", "PreToolUse"],
                                input=json.dumps(event), env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertDenied(json.loads(result.stdout))

    def test_satisfied_attachment_uses_frozen_paths_but_unresolved_alias_changes_fail_closed(self):
        alias = self.workspace / "link.py"
        alias.symlink_to(self.target)
        paths = checkpoints.normalize_dependent_paths(self.workspace, ["link.py"])
        self.begin(paths)
        completed = self.attach(paths=paths)
        self.begin(paths, "b" * 32)
        unresolved = self.attach(self.job(number=2), paths, "b" * 32)
        checkpoints.record_review(completed, {"job_id": completed["job_id"], "status": "completed",
                                               "advice": "Review of the original target."}, self.state)
        alias.unlink()
        alias.symlink_to(self.workspace / "new-target.py")
        checkpoints.attach_dependencies(self.scope, self.attempt, completed, self.state)
        for changed in (completed | {"dependent_paths": [str(alias)]}, completed | {"job_id": "f" * 64}):
            with self.subTest(changed=changed), self.assertRaises(checkpoints.CheckpointError):
                checkpoints.attach_dependencies(self.scope, self.attempt, changed, self.state)
        with self.assertRaises(checkpoints.CheckpointError):
            checkpoints.attach_dependencies(self.scope, "b" * 32, unresolved, self.state)
        database = next((self.state / "checkpoints" / "dependencies").glob("*.sqlite3"))
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT satisfied FROM requirements ORDER BY attempt_id").fetchall(), [(1,), (0,)])


if __name__ == "__main__":
    unittest.main()
