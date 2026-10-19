import asyncio
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

from test_mcp import tool_result


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"


@unittest.skipIf(os.name == "nt", "Fake executables and detached workers use POSIX")
class UsageFallbackMCPTests(unittest.IsolatedAsyncioTestCase):
    async def exercise_handoff(self, root, *, alternate_fails):
        root = root.resolve()
        workspace = root / "workspace"
        workspace.mkdir()
        cli = root / ".zcode/cli"
        (cli / "db").mkdir(parents=True)
        (cli / "rollout").mkdir()
        with sqlite3.connect(cli / "db/db.sqlite") as database:
            database.execute("CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT)")
            database.execute("INSERT INTO session VALUES (?, ?)", ("sess_quota_fixture", str(workspace)))
        request = {"provider": "claude", "stage": "before_plan", "dependent_paths": ["dependent.py"],
                   "question": "Review the synthetic dependent change before implementation."}
        messages = [{"role": "system", "content": "Synthetic quota lifecycle fixture."},
                    {"role": "user", "content": "Preserve the dependent-path boundary."}]
        entry = {
            "type": "model_io", "sessionId": "sess_quota_fixture", "turnId": "turn_quota_fixture",
            "querySource": "main_turn", "requestId": "req_quota_fixture",
            "request": {"messages": messages, "sdkMessages": messages,
                        "body": {"messages": messages, "tools": [{"name": "consult_advisor"}]}},
            "response": {"toolCalls": [{"id": "call_quota_fixture", "name": "mcp__advisor__consult_advisor",
                                        "input": {"request": request}}]},
        }
        (cli / "rollout/model-io-sess_quota_fixture.jsonl").write_text(json.dumps(entry) + "\n")
        bin_dir = root / "bin"
        bin_dir.mkdir()
        fake_source = textwrap.dedent('''\
            import hashlib
            import json
            import os
            from pathlib import Path
            import sys
            import time

            root = Path(os.environ["ADVISOR_TEST_ROOT"])
            provider = Path(sys.argv[0]).name
            prompt = sys.stdin.read()
            record = {"provider": provider, "arguments": sys.argv[1:]}
            if provider == "codex":
                context_file = json.loads(next(arg.split("=", 1)[1] for arg in sys.argv
                                               if arg.startswith("model_instructions_file=")))
                prompt = Path(context_file).read_text()
                journals = list((root / "state/jobs").glob("*/provider_attempts.json"))
                record["journal_before_launch"] = [json.loads(path.read_text()) for path in journals]
            record["context_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
            with (root / "calls.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\\n")
            if provider == "claude":
                print(json.dumps({"type": "result", "session_id": "quota-primary-fixture",
                                  "subtype": "success", "is_error": True, "api_error_status": 429,
                                  "api_error": "usage_limit_reached", "api_error_origin": "first_party",
                                  "result": "Synthetic quota refusal"}), flush=True)
                raise SystemExit(1)
            (root / "alternate-started").touch()
            deadline = time.monotonic() + 12
            while not (root / "release").exists():
                if time.monotonic() > deadline:
                    raise SystemExit("Synthetic alternate release timed out")
                time.sleep(0.02)
            if os.environ["ADVISOR_TEST_ALTERNATE_FAILS"] == "1":
                raise SystemExit("Synthetic alternate failure")
            for event in [
                {"type": "thread.started", "thread_id": "quota-alternate-fixture"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "Use the verified approach."}},
                {"type": "turn.completed"},
            ]:
                print(json.dumps(event), flush=True)
            ''')
        for provider in ("claude", "codex"):
            executable = bin_dir / provider
            executable.write_text(f"#!{sys.executable}\n" + fake_source)
            executable.chmod(0o700)
        config = root / "config.json"
        config.write_text(json.dumps({"usage_fallback": True}))
        environment = {**os.environ, "HOME": str(root), "PATH": str(bin_dir),
                       "CODEX_HOME": str(root / "codex-home"), "CLAUDE_CONFIG_DIR": str(root / "claude-home"),
                       "ADVISOR_CONFIG": str(config), "ADVISOR_STATE_DIR": str(root / "state"),
                       "ADVISOR_TEST_ROOT": str(root), "ADVISOR_TEST_ALTERNATE_FAILS": str(int(alternate_fails))}
        for key in ("ADVISOR_ACTIVE", "ZCODE_SESSION_DB_PATH", "ZCODE_SESSION_DB",
                    "CLAUDE_CODE_SKIP_PROMPT_HISTORY"):
            environment.pop(key, None)
        params = StdioServerParameters(command=sys.executable, args=[str(RUNTIME), "serve"], env=environment)
        meta = {"com.zcode/request-context": {"session_id": "sess_quota_fixture", "turn_id": "turn_quota_fixture",
                                              "workspace_path": str(workspace)}}

        async def wait_for_file(path):
            async with asyncio.timeout(5):
                while not path.exists():
                    await asyncio.sleep(0.02)

        async def dependent_checkpoint():
            event = {"session_id": "sess_quota_fixture", "turnId": "turn_quota_fixture",
                     "cwd": str(workspace), "hook_event_name": "PreToolUse", "tool_name": "Write",
                     "tool_input": {"file_path": str(workspace / "dependent.py")}}
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(RUNTIME), "review-checkpoint", "PreToolUse", env=environment,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            output, errors = await asyncio.wait_for(process.communicate(json.dumps(event).encode()), 3)
            self.assertEqual(process.returncode, 0, errors)
            return json.loads(output)

        def assert_quota(attempts):
            self.assertEqual(len(attempts), 1)
            self.assertEqual({key: attempts[0][key] for key in ("provider", "model", "effort", "status", "code")},
                             {"provider": "claude", "model": "claude-opus-5-5", "effort": "max",
                              "status": "usage_exhausted", "code": "usage_limit_reached"})
            self.assertEqual(attempts[0]["evidence"], "claude_first_party_terminal")
            self.assertTrue(attempts[0]["message"])

        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    job = tool_result(await session.call_tool("consult_advisor", {"request": request}, meta=meta))
                    self.assertEqual(job["status"], "pending")
                    directory = Path(job["advice_path"]).parent
                    metadata = (directory / "job.json").read_bytes()
                    snapshot_id = job["context_transfer"]["snapshot_id"]
                    snapshot = root / "state/contexts" / (snapshot_id + ".json")
                    frozen_context = snapshot.read_bytes()
                    self.assertTrue(json.loads((directory / "config.json").read_text())["usage_fallback"])
                    await wait_for_file(root / "alternate-started")
                    pending = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=meta))
                    self.assertEqual(pending["status"], "pending")
                    assert_quota(pending["provider_attempts"])
                    self.assertEqual(pending["context_transfer"]["snapshot_id"], snapshot_id)
                    self.assertEqual((await dependent_checkpoint())["hookSpecificOutput"]["permissionDecision"], "deny")

            # The detached worker must retain its frozen policy after server disconnect.
            config.write_text(json.dumps({"usage_fallback": False}))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    pending = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=meta))
                    self.assertEqual(pending["status"], "pending")
                    assert_quota(pending["provider_attempts"])
                    (root / "release").touch()
                    await wait_for_file(directory / "result.json")
                    self.assertEqual((await dependent_checkpoint())["hookSpecificOutput"]["permissionDecision"], "deny")
                    result = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=meta))
                    expected_status = "failed" if alternate_fails else "completed"
                    self.assertEqual(result["status"], expected_status)
                    self.assertEqual(result["job_id"], job["job_id"])
                    attempts = result["provider_attempts"]
                    assert_quota(attempts[:1])
                    self.assertEqual(attempts[1], {"provider": "codex", "model": "gpt-6.1-sol", "effort": "max",
                                                   "status": expected_status,
                                                   **({"error": attempts[1]["error"]} if alternate_fails else {})})
                    self.assertEqual(len(attempts), 2)
                    self.assertEqual(json.loads((directory / "provider_attempts.json").read_text()), attempts)
                    checkpoint = await dependent_checkpoint()
                    if alternate_fails:
                        self.assertIn("Synthetic alternate failure", result["error"])
                        self.assertEqual(checkpoint["hookSpecificOutput"]["permissionDecision"], "deny")
                        self.assertFalse((directory / "advice.md").exists())
                    else:
                        self.assertEqual(result["requested_provider"], "claude")
                        self.assertEqual(result["provider"], "codex")
                        self.assertEqual(result["model"], "gpt-6.1-sol")
                        self.assertEqual(result["effort"], "max")
                        self.assertEqual(result["advice"], "Use the verified approach.")
                        self.assertEqual(Path(result["advice_path"]).read_text(), "Use the verified approach.\n")
                        self.assertEqual(result["context_transfer"]["snapshot_id"], snapshot_id)
                        self.assertEqual(checkpoint, {})
                    repeated = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}, meta=meta))
                    self.assertEqual(repeated, result)

            self.assertEqual((directory / "job.json").read_bytes(), metadata)
            self.assertEqual(snapshot.read_bytes(), frozen_context)
            self.assertEqual(list((root / "state/jobs").iterdir()), [directory])
            records = [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]
            self.assertEqual([record["provider"] for record in records], ["claude", "codex"])
            self.assertEqual(records[0]["context_sha256"], records[1]["context_sha256"])
            assert_quota(records[1]["journal_before_launch"][0])
            self.assertEqual(len(records[1]["journal_before_launch"]), 1)
            for record, model in zip(records, ("claude-opus-5-5", "gpt-6.1-sol")):
                arguments = record["arguments"]
                self.assertEqual(arguments[arguments.index("--model") + 1], model)
                self.assertNotIn("resume", arguments)
            claude_args = records[0]["arguments"]
            self.assertEqual(claude_args[claude_args.index("--effort") + 1], "max")
            self.assertIn('model_reasoning_effort="max"', records[1]["arguments"])
        finally:
            (root / "release").touch()

    async def test_usage_handoff_survives_stdio_disconnect_and_releases_only_after_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            await asyncio.wait_for(self.exercise_handoff(Path(directory), alternate_fails=False), 25)

    async def test_failed_alternate_keeps_original_job_journal_and_dependent_paths_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            await asyncio.wait_for(self.exercise_handoff(Path(directory), alternate_fails=True), 25)


if __name__ == "__main__":
    unittest.main()
