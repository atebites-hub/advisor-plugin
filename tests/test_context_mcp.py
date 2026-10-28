import asyncio
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import textwrap
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_mcp import completed_advice, tool_result


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"


@unittest.skipIf(os.name == "nt", "Fake executable uses a POSIX shebang")
class NativeContextMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_context_is_bound_private_frozen_and_forwarded_over_stdio(self):
        async def exercise(root):
            workspace = root / "workspace"
            workspace.mkdir()
            cli = root / ".zcode/cli"
            (cli / "db").mkdir(parents=True)
            (cli / "rollout").mkdir()
            database = sqlite3.connect(cli / "db/db.sqlite")
            try:
                database.execute("CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT)")
                database.execute("INSERT INTO session VALUES (?, ?)", ("sess_native_fixture", str(workspace)))
                database.commit()
            finally:
                database.close()
            request = {"provider": "codex", "question": "Review the proposed implementation", "stage": "before_plan",
                       "dependent_paths": ["dependent.py"]}
            tool = {"id": "call_native_fixture", "name": "mcp__advisor__consult_advisor", "input": {"request": request}}
            entry = {
                "type": "model_io", "sessionId": "sess_native_fixture", "turnId": "turn_native_fixture",
                "querySource": "main_turn", "requestId": "req_native_fixture",
                "request": {
                    "messages": [
                        {"role": "system", "content": "system-policy-canary"},
                        {"role": "assistant", "content": [{"type": "reasoning", "text": "protected-reasoning-canary", "signature": "native-signature-canary"}, {"type": "text", "text": "Visible prior work"}]},
                        {"role": "tool", "content": [{"type": "tool-result", "toolCallId": "earlier_call", "output": {"evidence": "earlier-tool-result-canary", "password": "credential-value-canary"}}]},
                    ],
                    "body": {"system": "native-system-canary", "tools": [{"name": "consult_advisor", "description": "tool-schema-canary", "input_schema": {"type": "object", "properties": {"password": {"type": "string"}}}}]},
                    "headers": {"Authorization": "credential-header-canary"},
                },
                "response": {"text": "current-visible-response-canary", "reasoningText": "protected-response-canary", "toolCalls": [tool]},
            }
            entry["request"]["sdkMessages"] = copy.deepcopy(entry["request"]["messages"]) + [
                {"role": "assistant", "content": [{"type": "reasoning", "text": "sdk-reasoning-canary", "signature": "sdk-signature-canary"},
                                                   {"type": "text", "text": "sdk-only-canary"}]}]
            entry["request"]["body"]["messages"] = copy.deepcopy(entry["request"]["messages"]) + [
                {"role": "assistant", "content": [{"type": "thinking", "thinking": "body-thinking-canary", "signature": "body-signature-canary"},
                                                   {"type": "text", "text": "body-only-canary"}]}]
            source = cli / "rollout/model-io-sess_native_fixture.jsonl"
            source.write_text(json.dumps(entry) + "\n")
            fake = root / "codex"
            fake.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                import json
                import os
                from pathlib import Path
                import sys
                import time

                root = Path(os.environ["ADVISOR_TEST_ROOT"])
                (root / "started").touch()
                deadline = time.monotonic() + 8
                while not (root / "release").exists():
                    if time.monotonic() > deadline:
                        raise SystemExit(1)
                    time.sleep(0.02)
                descriptor = os.open(root / "provider-prompt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as stream:
                    sys.stdin.read()
                    context_file = json.loads(next(arg.split("=", 1)[1] for arg in sys.argv if arg.startswith("model_instructions_file=")))
                    stream.write(Path(context_file).read_text())
                for event in [
                    {"type": "thread.started", "thread_id": "fake-advisor-native"},
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "Review complete"}},
                    {"type": "turn.completed"},
                ]:
                    print(json.dumps(event))
                '''))
            fake.chmod(0o700)
            (root / "config.json").write_text("{}")
            environment = {**os.environ, "HOME": str(root), "PATH": str(root),
                           "ADVISOR_TEST_ROOT": str(root), "ADVISOR_CONFIG": str(root / "config.json"),
                           "ADVISOR_STATE_DIR": str(root / "state"),
                           "ADVISOR_USE_APP_SETTINGS": "true",
                           "ADVISOR_CLAUDE_ENABLED": "false", "ADVISOR_CLAUDE_MODEL": "claude-opus-5-5",
                           "ADVISOR_CLAUDE_EFFORT": "max", "ADVISOR_CODEX_ENABLED": "true",
                           "ADVISOR_CODEX_MODEL": "gpt-6-astra", "ADVISOR_CODEX_EFFORT": "high",
                           "ADVISOR_CURSOR_ENABLED": "false", "ADVISOR_CURSOR_MODEL": "claude-opus-5-5-high",
                           "ADVISOR_CURSOR_EFFORT": "high"}
            for key in ("ADVISOR_ACTIVE", "ZCODE_SESSION_DB_PATH", "ZCODE_SESSION_DB"):
                environment.pop(key, None)
            params = StdioServerParameters(command=sys.executable, args=[str(RUNTIME), "serve"], env=environment)
            meta = {"com.zcode/request-context": {"session_id": "sess_native_fixture", "turn_id": "turn_native_fixture", "workspace_path": str(workspace)}}

            async def checkpoint(raw=None, *, phase="PreToolUse", **changes):
                event = {"session_id": "sess_native_fixture", "turnId": "turn_native_fixture",
                         "cwd": str(workspace), "hook_event_name": phase, "tool_name": "Write",
                         "tool_input": {"file_path": str(workspace / "independent.py")}, **changes}
                process = await asyncio.create_subprocess_exec(
                    sys.executable, str(RUNTIME), "review-checkpoint", phase, env=environment,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                output, errors = await process.communicate(raw if raw is not None else json.dumps(event).encode())
                self.assertEqual(process.returncode, 0, errors)
                return json.loads(output)

            waiter = None
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        missing_paths = {key: value for key, value in request.items() if key != "dependent_paths"}
                        invalid_boundary = await session.call_tool("consult_advisor", {"request": missing_paths}, meta=meta)
                        self.assertTrue(invalid_boundary.isError)
                        self.assertIn("dependent_paths", str(invalid_boundary.content))
                        self.assertFalse((root / "started").exists())
                        status_entry = copy.deepcopy(entry)
                        status_entry["response"]["toolCalls"] = [{"id": "status_native", "name": "mcp__advisor__advisor_status", "input": {}}]
                        status_entry["request"].update(messagesKind="full", messageCount=3, messageOffset=0)
                        del status_entry["request"]["sdkMessages"]
                        del status_entry["request"]["body"]["messages"]
                        source.write_text(json.dumps(status_entry) + "\n")
                        status = tool_result(await session.call_tool("advisor_status", {}, meta=meta))
                        self.assertFalse(status["advisors"]["claude"]["enabled"])
                        self.assertEqual(status["advisors"]["codex"]["model"], "gpt-6-astra")
                        self.assertEqual(status["advisors"]["codex"]["effort"], "high")
                        self.assertEqual(status["native_context"]["recording_mode"], "bounded")
                        self.assertFalse(status["native_context"]["long_session_ready"])
                        source.write_text(json.dumps(entry) + "\n")
                        wrong_scope = await session.call_tool("consult_advisor", {"request": request | {"workspace": str(root)}}, meta=meta)
                        self.assertTrue(wrong_scope.isError)
                        ambiguous = copy.deepcopy(entry)
                        ambiguous["response"]["toolCalls"].append(tool)
                        source.write_text(json.dumps(ambiguous) + "\n")
                        duplicate = await session.call_tool("consult_advisor", {"request": request}, meta=meta)
                        self.assertTrue(duplicate.isError)
                        self.assertFalse((root / "started").exists())
                        readonly_request = {**request, "dependent_paths": []}
                        for recording_mode in ("bounded", "unknown"):
                            refused = copy.deepcopy(entry)
                            refused["response"]["toolCalls"][0]["input"] = {"request": request}
                            if recording_mode == "bounded":
                                refused["request"].update(messagesKind="full", messageCount=3, messageOffset=0)
                            else:
                                del refused["request"]["sdkMessages"]
                                del refused["request"]["body"]["messages"]
                            source.write_text(json.dumps(entry) + "\n" + json.dumps(refused) + "\n")
                            rejected = await session.call_tool("consult_advisor", {"request": request}, meta=meta)
                            self.assertTrue(rejected.isError)
                            self.assertIn("Keep complete model I/O", str(rejected.content))
                            self.assertEqual(await checkpoint(), {})
                            self.assertEqual(await checkpoint(tool_input={"file_path": str(workspace / "dependent.py")}), {})
                            self.assertEqual(await checkpoint(phase="Stop"), {})
                            self.assertFalse((root / "started").exists())
                            self.assertFalse(list((root / "state/jobs").glob("*")))
                            self.assertFalse(list((root / "state/contexts").glob("*")))
                        early_tail = copy.deepcopy(entry)
                        early_tail["request"].update(messagesKind="tail", messageCount=4, messageOffset=1)
                        early_tail["response"]["toolCalls"][0]["input"] = {"request": readonly_request}
                        source.write_text(json.dumps(early_tail) + "\n")
                        early_unavailable = tool_result(await session.call_tool("consult_advisor", {"request": readonly_request}, meta=meta))
                        self.assertEqual(early_unavailable["status"], "unavailable")
                        self.assertEqual(await checkpoint(), {})
                        self.assertFalse((root / "started").exists())
                        source.write_text(json.dumps(entry) + "\n")
                        job = tool_result(await session.call_tool("consult_advisor", {"request": request}, meta=meta))
                        self.assertEqual(job["context_transfer"]["mode"], "native_snapshot")
                        descriptor = json.loads((Path(job["advice_path"]).parent / "job.json").read_text())
                        self.assertEqual(descriptor["dependency_attempt_id"], job["context_transfer"]["snapshot_id"])
                        watcher = job["completion_watcher"]
                        self.assertEqual(watcher["tool"], "Bash")
                        self.assertTrue(watcher["input"]["run_in_background"])
                        for required in (job["job_id"], "read_advice"):
                            self.assertIn(required, watcher["input"]["description"])
                        independent = await checkpoint()
                        self.assertNotEqual(independent["hookSpecificOutput"].get("permissionDecision"), "deny")
                        self.assertIn("independent", independent["hookSpecificOutput"]["additionalContext"])
                        dependent = {"file_path": str(workspace / "dependent.py")}
                        self.assertEqual((await checkpoint(tool_input=dependent))["hookSpecificOutput"]["permissionDecision"], "deny")
                        self.assertEqual((await checkpoint(phase="Stop"))["decision"], "block")
                        watching = await checkpoint(phase="PostToolUse", tool_name="Bash",
                            tool_input=watcher["input"], tool_response={"status": "backgrounded", "interrupted": False,
                                                                     "backgroundTaskId": "bg_native_waiter_fixture"})
                        self.assertIn("independent", watching["hookSpecificOutput"]["additionalContext"])
                        self.assertIn("waiting", (await checkpoint(phase="Stop"))["systemMessage"])
                        waiter = await asyncio.create_subprocess_exec(sys.executable, str(RUNTIME), "wait", job["job_id"],
                            env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                        snapshot_id = job["context_transfer"]["snapshot_id"]
                        snapshot_path = root / "state/contexts" / (snapshot_id + ".json")
                        frozen = snapshot_path.read_bytes()
                        snapshot = json.loads(frozen)
                        self.assertEqual(snapshot["binding"], {"host": "zcode", "session_id": "sess_native_fixture", "workspace": str(workspace.resolve())})
                        async with asyncio.timeout(3):
                            while not (root / "started").exists():
                                await asyncio.sleep(0.02)
                        source.write_text(json.dumps(entry).replace("earlier-tool-result-canary", "late-host-mutation-canary") + "\n")
                        (root / "release").touch()
                        result = await completed_advice(session, job)
                        self.assertEqual(result["context_transfer"]["snapshot_id"], snapshot_id)
                        self.assertEqual(result["advice"], "Review complete")
                        self.assertEqual((result["model"], result["effort"]), ("gpt-6-astra", "high"))
                        ready, errors = await asyncio.wait_for(waiter.communicate(), 7)
                        self.assertEqual(waiter.returncode, 0, errors)
                        self.assertEqual(json.loads(ready)["status"], "completed")
                        self.assertNotIn(b"Review complete", ready)
                        self.assertEqual((await checkpoint(tool_input=dependent, turnId="turn_native_wake"))["hookSpecificOutput"]["permissionDecision"], "deny")
                        for phase in ("PostToolUse", "PostToolUseFailure", "PostToolUse"):
                            alert = await checkpoint(phase=phase, tool_name="Read")
                            context = alert["hookSpecificOutput"]["additionalContext"]
                            self.assertIn(job["job_id"], context)
                            self.assertIn("read_advice", context)
                            self.assertNotIn("Review complete", context)
                        self.assertEqual((await checkpoint(phase="Stop"))["decision"], "block")
                        self.assertEqual((await checkpoint(b"invalid-json"))["hookSpecificOutput"]["permissionDecision"], "deny")
                        for malformed in (b'{"hook_event_name":null}', b'{"hook_event_name":"Stop"}'):
                            self.assertEqual((await checkpoint(malformed))["hookSpecificOutput"]["permissionDecision"], "deny")
                        foreign_meta = copy.deepcopy(meta)
                        foreign_meta["com.zcode/request-context"]["session_id"] = "sess_foreign"
                        denied = await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=foreign_meta)
                        self.assertTrue(denied.isError)
                        self.assertNotIn("Review complete", str(denied.content))
                        wake_meta = copy.deepcopy(meta)
                        wake_meta["com.zcode/request-context"]["turn_id"] = "turn_native_wake"
                        bounded_after_submit = copy.deepcopy(entry)
                        bounded_after_submit["request"].update(messagesKind="full", messageCount=3, messageOffset=0)
                        source.write_text(json.dumps(bounded_after_submit) + "\n")
                        awakened = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=wake_meta))
                        self.assertEqual(awakened["advice"], "Review complete")
                        self.assertEqual(await checkpoint(turnId="turn_native_wake"), {})
                        self.assertEqual(await checkpoint(tool_input=dependent, turnId="turn_native_wake"), {})
                        self.assertEqual(await checkpoint(phase="PostToolUse", tool_name="Read"), {})
                        review_rows = []
                        for path in (root / "state/checkpoints").glob("*.sqlite3"):
                            with sqlite3.connect(path) as database:
                                review_rows.extend(database.execute("SELECT job_id FROM reviews").fetchall())
                        self.assertEqual(review_rows, [(job["job_id"],)])
                        retrieved = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=meta))
                        self.assertEqual(retrieved["advice"], "Review complete")
                        self.assertEqual(await checkpoint(), {})
                        self.assertEqual((await checkpoint(phase="Stop"))["decision"], "block")
                        jobs_before = set((root / "state/jobs").iterdir())
                        snapshots_before = set((root / "state/contexts").iterdir())

                        def retained_tail(arguments):
                            tail = copy.deepcopy(entry)
                            tail["requestId"] = "req_final_tail"
                            tail["request"].update(messagesKind="tail", messageCount=80, messageOffset=16,
                                                   messages=[{"role": "user", "content": "retained"}] * 64)
                            tail["response"]["toolCalls"][0]["input"] = {"request": arguments}
                            source.write_text(json.dumps(entry) + "\n" + json.dumps(tail) + "\n")

                        final_request = {"provider": "codex", "question": "Review the saved and tested result", "stage": "during_task",
                                         "dependent_paths": ["dependent.py"]}
                        retained_tail(final_request)
                        unverified_meta = copy.deepcopy(meta)
                        unverified_meta["com.zcode/request-context"]["workspace_path"] = str(root)
                        unverified = await session.call_tool("consult_advisor", {"request": final_request}, meta=unverified_meta)
                        self.assertTrue(unverified.isError)
                        self.assertEqual((await checkpoint(phase="Stop"))["decision"], "block")
                        malformed = {**final_request, "question": 3}
                        retained_tail(malformed)
                        invalid = await session.call_tool("consult_advisor", {"request": malformed}, meta=meta)
                        self.assertTrue(invalid.isError)
                        self.assertEqual((await checkpoint(phase="Stop"))["decision"], "block")
                        retained_tail(final_request)
                        unavailable = tool_result(await session.call_tool("consult_advisor", {"request": final_request}, meta=meta))
                        self.assertEqual(unavailable["status"], "unavailable")
                        self.assertFalse(unavailable["provider_started"])
                        self.assertFalse(unavailable["review_complete"])
                        self.assertNotIn("job_id", unavailable)
                        self.assertIn("incomplete", (await checkpoint(phase="Stop"))["systemMessage"])
                        self.assertEqual((await checkpoint(tool_input=dependent, turnId="turn_later"))["hookSpecificOutput"]["permissionDecision"], "deny")
                        self.assertNotEqual((await checkpoint())["hookSpecificOutput"].get("permissionDecision"), "deny")
                        self.assertEqual(set((root / "state/jobs").iterdir()), jobs_before)
                        self.assertEqual(set((root / "state/contexts").iterdir()), snapshots_before)
                prompt = (root / "provider-prompt").read_text()
                for canary in ("system-policy-canary", "native-system-canary", "tool-schema-canary", "earlier-tool-result-canary", "current-visible-response-canary"):
                    self.assertIn(canary, prompt)
                for excluded in ("protected-reasoning-canary", "native-signature-canary", "protected-response-canary", "credential-value-canary",
                                 "credential-header-canary", "late-host-mutation-canary", "sdk-reasoning-canary", "sdk-signature-canary",
                                 "sdk-only-canary", "body-thinking-canary", "body-signature-canary", "body-only-canary"):
                    self.assertNotIn(excluded, prompt)
                    self.assertNotIn(excluded.encode(), frozen)
                self.assertEqual(snapshot_path.read_bytes(), frozen)
                self.assertEqual((root / "provider-prompt").stat().st_mode & 0o777, 0o600)
            finally:
                (root / "release").touch()
                if waiter is not None and waiter.returncode is None:
                    waiter.kill()
                    await waiter.communicate()

        with tempfile.TemporaryDirectory() as directory:
            await asyncio.wait_for(exercise(Path(directory)), timeout=20)


if __name__ == "__main__":
    unittest.main()
