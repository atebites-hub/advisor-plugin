import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"


def tool_result(result):
    if result.isError:
        raise AssertionError(result.content)
    return json.loads(next(item.text for item in result.content if item.type == "text"))


async def completed_advice(session, job):
    async with asyncio.timeout(10):
        while job["status"] == "pending":
            await asyncio.sleep(0.03)
            job = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}))
    if job["status"] != "completed":
        raise AssertionError(job)
    return job


class MCPTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipIf(os.name == "nt", "Fake executable uses a POSIX shebang")
    async def test_stdio_consultation_resumes_and_deduplicates_using_real_child_process(self):
        async def exercise(root):
            bin_dir = root / "bin"
            bin_dir.mkdir()
            log = root / "provider-calls.jsonl"
            fake_codex = bin_dir / "codex"
            fake_codex.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                import json
                import os
                from pathlib import Path
                import sys

                arguments = sys.argv[1:]
                log = Path(os.environ["ADVISOR_TEST_LOG"])
                count = len(log.read_text().splitlines()) + 1 if log.exists() else 1
                native_id = arguments[arguments.index("resume") + 1] if "resume" in arguments else "fake-native-1"
                sys.stdin.read()
                context_file = json.loads(next(arg.split("=", 1)[1] for arg in arguments if arg.startswith("model_instructions_file=")))
                record = {"arguments": arguments, "prompt": Path(context_file).read_text(),
                          "active": os.environ.get("ADVISOR_ACTIVE"), "cwd": os.getcwd()}
                with log.open("a") as stream:
                    stream.write(json.dumps(record) + "\\n")
                for event in [
                    {"type": "thread.started", "thread_id": native_id},
                    {"type": "item.completed", "item": {"type": "agent_message", "text": f"Advice {count}"}},
                    {"type": "turn.completed"},
                ]:
                    print(json.dumps(event))
                '''))
            fake_codex.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": str(bin_dir),
                "ADVISOR_CONFIG": str(root / "absent-config.json"),
                "ADVISOR_STATE_DIR": str(root / "state"),
                "ADVISOR_TEST_LOG": str(log),
            }
            environment.pop("ADVISOR_ACTIVE", None)
            params = StdioServerParameters(
                command=sys.executable, args=[str(RUNTIME), "serve"], env=environment
            )
            request = {
                "workspace": str(root), "provider": "codex", "host": "codex",
                "session_id": "worker-session", "task_id": "integration-task",
                "stage": "before_plan", "question": "First uncertainty?",
                "context": "A fake executable supplies deterministic advice.",
            }
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    results = []
                    for question in ("First uncertainty?", "Second uncertainty?", "Second uncertainty?"):
                        result = await session.call_tool("consult_advisor", {"request": request | {"question": question}})
                        results.append(await completed_advice(session, tool_result(result)))
            self.assertEqual([item["advice"] for item in results], ["Advice 1", "Advice 2", "Advice 2"])
            self.assertEqual([item["cached"] for item in results], [False, False, True])
            self.assertEqual([item["remaining_consults"] for item in results], [4, 3, 3])
            self.assertEqual({item["advisor_session_id"] for item in results}, {"fake-native-1"})
            records = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertNotIn("resume", records[0]["arguments"])
            arguments = records[1]["arguments"]
            self.assertEqual(arguments[arguments.index("resume") + 1], "fake-native-1")
            for record, question in zip(records, ("First uncertainty?", "Second uncertainty?")):
                self.assertEqual(record["active"], "1")
                self.assertIn(question, record["prompt"])
                self.assertNotIn(record["prompt"], record["arguments"])
                self.assertNotEqual(record["cwd"], str(root))

        with tempfile.TemporaryDirectory() as directory:
            await asyncio.wait_for(exercise(Path(directory)), timeout=20)

    async def test_stdio_initializes_lists_tools_and_rejects_recursive_consult(self):
        async def exercise(workspace):
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(RUNTIME), "serve"],
                env={**os.environ, "ADVISOR_ACTIVE": "1"},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual(
                        {tool.name for tool in tools.tools},
                        {"consult_advisor", "read_advice", "advisor_status"},
                    )
                    missing_selection = await session.call_tool("consult_advisor", {"request": {}})
                    self.assertTrue(missing_selection.isError)
                    message = " ".join(getattr(item, "text", "") for item in missing_selection.content)
                    self.assertIn("provider", message.lower())
                    result = await session.call_tool(
                        "consult_advisor",
                        {
                            "request": {
                                "workspace": workspace,
                                "provider": "claude",
                                "host": "claude",
                                "session_id": "smoke-session",
                                "task_id": "smoke-task",
                                "stage": "before_plan",
                                "question": "Do I need advice?",
                                "context": "This test must not invoke a model.",
                            }
                        },
                    )
                    self.assertTrue(result.isError)
                    message = " ".join(getattr(item, "text", "") for item in result.content)
                    self.assertRegex(message.lower(), "recurs|active|nested")

        with tempfile.TemporaryDirectory() as workspace:
            await asyncio.wait_for(exercise(workspace), timeout=20)

    @unittest.skipIf(os.name == "nt", "Fake executable and detached process check use POSIX")
    async def test_background_job_stays_responsive_and_finishes_after_stdio_disconnect(self):
        async def exercise(root):
            fake_codex = root / "codex"
            fake_codex.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
                import json
                import os
                from pathlib import Path
                import sys
                import time

                root = Path(os.environ["ADVISOR_TEST_ROOT"])
                sys.stdin.read()
                with (root / "calls").open("a") as stream:
                    stream.write("called\\n")
                deadline = time.monotonic() + 8
                while not (root / "release").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                for event in [
                    {"type": "thread.started", "thread_id": "fake-detached-1"},
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "Advice survives disconnect."}},
                    {"type": "turn.completed"},
                ]:
                    print(json.dumps(event))
                '''))
            fake_codex.chmod(0o755)
            environment = {**os.environ, "PATH": str(root), "ADVISOR_TEST_ROOT": str(root),
                           "ADVISOR_STATE_DIR": str(root / "state"),
                           "ADVISOR_CONFIG": str(root / "absent.json")}
            environment.pop("ADVISOR_ACTIVE", None)
            params = StdioServerParameters(command=sys.executable, args=[str(RUNTIME), "serve"], env=environment)
            request = {"provider": "codex", "workspace": str(root), "host": "zcode",
                       "session_id": "worker", "task_id": "background-task", "stage": "before_plan",
                       "question": "Does a detached job survive?", "context": "Synthetic test only."}
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        job = tool_result(await asyncio.wait_for(session.call_tool("consult_advisor", {"request": request}), 2))
                        self.assertEqual(job["status"], "pending")
                        async with asyncio.timeout(3):
                            while not (root / "calls").exists():
                                await asyncio.sleep(0.02)
                        pending = tool_result(await asyncio.wait_for(session.call_tool("read_advice", {"job_id": job["job_id"]}), 0.5))
                        self.assertEqual(pending["status"], "pending")
                        status = await asyncio.wait_for(session.call_tool("advisor_status"), 0.5)
                        self.assertFalse(status.isError)
                        duplicate = tool_result(await session.call_tool("consult_advisor", {"request": request}))
                        self.assertEqual(duplicate["job_id"], job["job_id"])
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        pending = tool_result(await session.call_tool("read_advice", {"job_id": job["job_id"]}))
                        self.assertEqual(pending["status"], "pending")
                        (root / "release").touch()
                        result = await completed_advice(session, pending)
                        self.assertEqual(result["advice"], "Advice survives disconnect.")
                        self.assertEqual(Path(result["advice_path"]).read_text(), "Advice survives disconnect.\n")
                        duplicate = tool_result(await session.call_tool("consult_advisor", {"request": request}))
                        self.assertEqual(duplicate["job_id"], job["job_id"])
                        self.assertTrue(duplicate["cached"])
                self.assertEqual((root / "calls").read_text().splitlines(), ["called"])
            finally:
                (root / "release").touch()

        with tempfile.TemporaryDirectory() as directory:
            await asyncio.wait_for(exercise(Path(directory)), timeout=20)


if __name__ == "__main__":
    unittest.main()
