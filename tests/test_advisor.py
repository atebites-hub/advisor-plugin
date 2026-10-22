import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_runtime_tests", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = advisor
SPEC.loader.exec_module(advisor)


class ProviderTests(unittest.TestCase):
    def test_commands_select_exact_models_and_max_effort(self):
        claude = advisor.provider_command("claude", "claude-opus-5-5", None)
        self.assertEqual(claude[claude.index("--model") + 1], "claude-opus-5-5")
        self.assertEqual(claude[claude.index("--effort") + 1], "max")
        self.assertEqual(claude[claude.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", claude)
        self.assertIn("--include-partial-messages", claude)
        self.assertEqual(claude[claude.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", claude)
        self.assertEqual(claude[claude.index("--setting-sources") + 1], "")
        codex = advisor.provider_command("codex", "gpt-6.1-sol", None)
        self.assertEqual(codex[codex.index("--model") + 1], "gpt-6.1-sol")
        self.assertIn('model_reasoning_effort="max"', codex)
        self.assertEqual(codex[codex.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", codex)
        self.assertEqual(codex[codex.index("memories") - 1], "--disable")
        self.assertEqual(codex[-1], "-")

    def test_commands_resume_only_the_supplied_native_session(self):
        claude = advisor.provider_command("claude", "claude-opus-5-5", "native-1")
        self.assertEqual(claude[claude.index("--resume") + 1], "native-1")
        codex = advisor.provider_command("codex", "gpt-6.1-sol", "native-2")
        self.assertEqual(codex[codex.index("resume") + 1], "native-2")
        for provider, model, session in [
            ("claude", "other-model", None),
            ("codex", "claude-opus-5-5", None),
            ("both", "gpt-6.1-sol", None),
            ("claude", "claude-opus-5-5", "--unsafe"),
            ("codex", "gpt-6.1-sol", "bad\nsession"),
        ]:
            with self.subTest(provider=provider, model=model, session=session):
                with self.assertRaises(advisor.AdvisorError):
                    advisor.provider_command(provider, model, session)

    def test_claude_result_requires_success_advice_and_session(self):
        response = {"type": "result", "subtype": "success", "result": "Use A.", "session_id": "native-1"}
        self.assertEqual(advisor.parse_response("claude", json.dumps(response)), ("Use A.", "native-1"))
        for model in ("claude-opus-5-5", "claude-opus-5-5-20261001"):
            self.assertEqual(advisor.parse_response("claude", json.dumps(response | {"modelUsage": {model: {}}})), ("Use A.", "native-1"))
        invalid = [
            "invalid json", "[]", "null",
            json.dumps(response | {"is_error": True}),
            json.dumps(response | {"subtype": "error_max_turns"}),
            json.dumps(response | {"result": ""}),
            json.dumps(response | {"session_id": None}),
            json.dumps(response | {"session_id": "bad session"}),
            json.dumps(response | {"session_id": "--unsafe"}),
            json.dumps(response | {"modelUsage": {"different-model": {}}}),
            json.dumps(response | {"modelUsage": {"claude-opus-5-50": {}}}),
        ]
        for stdout in invalid:
            with self.subTest(stdout=stdout), self.assertRaises(advisor.AdvisorError):
                advisor.parse_response("claude", stdout)

    def test_claude_stream_uses_only_a_terminal_success_result(self):
        result = {"type": "result", "subtype": "success", "result": "Use A.",
                  "session_id": "native-1", "modelUsage": {"claude-opus-5-5": {}}}
        events = [
            {"type": "system", "subtype": "init"},
            {"type": "stream_event", "event": {"delta": {"type": "thinking_delta", "thinking": "Private reasoning"}}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "Partial advice"}]}},
            result,
        ]
        self.assertEqual(advisor.parse_response("claude", "\n".join(map(json.dumps, events))),
                         ("Use A.", "native-1"))
        for invalid in (events[:-1], events + [{"type": "system"}], events + [result]):
            with self.subTest(events=invalid), self.assertRaises(advisor.AdvisorError):
                advisor.parse_response("claude", "\n".join(map(json.dumps, invalid)))

    def test_codex_result_collects_agent_messages_from_completed_turn(self):
        events = [
            {"type": "thread.started", "thread_id": "native-2"},
            {"type": "item.completed", "item": {"type": "reasoning", "text": "Internal reasoning"}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Use A."}},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Verify B."}},
            {"type": "turn.completed", "usage": {}},
        ]
        stdout = "\n".join(json.dumps(event) for event in events) + "\n"
        self.assertEqual(advisor.parse_response("codex", stdout), ("Use A.\n\nVerify B.", "native-2"))
        for invalid in [
            events[:-1], events[1:], events[:1] + events[-1:],
            events + [{"type": "turn.failed", "error": {"message": "Failed"}}],
            events + [{"type": "error", "message": "Failed"}],
            events + [{"type": "item.completed", "item": {"type": "agent_message", "text": "Unreviewed trailing advice"}}],
            events + [{"type": "turn.started"}],
        ]:
            with self.subTest(events=invalid), self.assertRaises(advisor.AdvisorError):
                advisor.parse_response("codex", "\n".join(json.dumps(event) for event in invalid))
        with self.assertRaises(advisor.AdvisorError):
            advisor.parse_response("codex", "invalid json")
        for failure in ({"type": "error"}, {"type": "turn.failed"}):
            with self.subTest(failure=failure), self.assertRaisesRegex(advisor.AdvisorError, "Codex could not complete"):
                advisor.parse_response("codex", "\n".join(map(json.dumps, events[:-1] + [failure] + events[-1:])))
        events[0]["thread_id"] = "--unsafe"
        with self.assertRaises(advisor.AdvisorError):
            advisor.parse_response("codex", "\n".join(json.dumps(event) for event in events))

    def test_jsonl_preserves_unicode_separators_in_advice(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            advice = "First" + separator + "Second"
            streams = {
                "claude": [{"type": "result", "subtype": "success", "result": advice, "session_id": "native-unicode"}],
                "codex": [{"type": "thread.started", "thread_id": "native-unicode"},
                          {"type": "item.completed", "item": {"type": "agent_message", "text": advice}},
                          {"type": "turn.completed"}],
            }
            for provider, events in streams.items():
                with self.subTest(provider=provider, separator=repr(separator)):
                    stdout = "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n\n"
                    self.assertEqual(advisor.parse_response(provider, stdout), (advice, "native-unicode"))

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_process_isolates_context_and_blocks_recursive_credentials(self, capture, popen, which):
        claude_output = json.dumps({"result": "Use A.", "session_id": "native-1"})
        codex_output = "\n".join(json.dumps(event) for event in [
            {"type": "thread.started", "thread_id": "native-1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Use A."}},
            {"type": "turn.completed"},
        ])
        cases = [
            ("claude", "claude-opus-5-5", None, claude_output),
            ("codex", "gpt-6.1-sol", None, codex_output),
            ("codex", "gpt-6.1-sol", "native-1", codex_output),
        ]
        for name, model, native_id, stdout in cases:
            with self.subTest(provider=name, resume=native_id):
                popen.reset_mock()
                capture.reset_mock()
                which.return_value = f"/mock/bin/{name}"
                process = popen.return_value
                process.returncode = 0
                context_paths = []

                def capture_output(process, stdin, timeout, progress, **options):
                    if name == "codex":
                        path = self.codex_context_path(popen.call_args.args[0])
                        self.assertEqual(path.read_bytes(), b"Private context packet")
                        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
                        context_paths.append(path)
                    return stdout.encode(), b""

                capture.side_effect = capture_output
                environment = {key: "private-value" for key in ("CLAUDECODE", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY")}
                environment["CLAUDE_CODE_EFFORT_LEVEL"] = "low"
                environment["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"] = "0"
                with patch.dict(os.environ, environment):
                    os.environ.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)
                    result = advisor.run_provider(name, model, "Private context packet", Path.cwd(), native_id, 17,
                                                  question="Which plan should I use?")
                    self.assertEqual(os.environ["CLAUDE_CODE_EFFORT_LEVEL"], "low")
                    self.assertEqual(os.environ["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"], "0")
                self.assertEqual(result, ("Use A.", "native-1"))
                command = popen.call_args.args[0]
                self.assertEqual(command[0], f"/mock/bin/{name}")
                self.assertNotIn("Private context packet", command)
                kwargs = popen.call_args.kwargs
                self.assertEqual(kwargs["env"]["ADVISOR_ACTIVE"], "1")
                for key in ("CLAUDECODE", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
                    self.assertNotIn(key, kwargs["env"])
                if name == "claude":
                    self.assertEqual(kwargs["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "max")
                    self.assertEqual(kwargs["env"]["CLAUDE_CODE_DISABLE_ADVISOR_TOOL"], "1")
                self.assertNotEqual(Path(kwargs["cwd"]), Path.cwd())
                if name == "codex":
                    self.assertEqual(command[command.index("--cd") + 1], kwargs["cwd"])
                    self.assertEqual(context_paths[0].parent, Path(kwargs["cwd"]))
                    self.assertFalse(context_paths[0].exists())
                self.assertEqual(kwargs["stdin"], subprocess.PIPE)
                stdin = (b"Advisor consultation question:\nWhich plan should I use?" if name == "codex"
                         else b"Private context packet")
                capture.assert_called_once_with(process, stdin, 17, None, provider=name,
                                                idle_timeout_seconds=1200, absolute_deadline=None)
                popen.assert_called_once()

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_claude_temp_is_private_and_cleaned_for_fresh_and_resumed_consults(self, capture, popen, which):
        inherited = "/inherited/shared-claude-temp"
        output = json.dumps({"result": "Use A.", "session_id": "native-1"}).encode()
        for native_id in (None, "native-1"):
            for outcome in ("success", "spawn", "timeout", "exit"):
                with self.subTest(resume=native_id, outcome=outcome):
                    popen.reset_mock()
                    capture.reset_mock()
                    process = popen.return_value
                    process.returncode = 1 if outcome == "exit" else 0
                    directories = []

                    def launch(command, **kwargs):
                        directory = Path(kwargs["cwd"])
                        directories.append(directory)
                        self.assertEqual(Path(kwargs["env"]["CLAUDE_CODE_TMPDIR"]), directory)
                        self.assertTrue(directory.is_dir())
                        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
                        self.assertEqual(kwargs["env"]["CLAUDE_CONFIG_DIR"], "/persistent/claude-auth")
                        if outcome == "spawn":
                            raise OSError("Cannot execute")
                        return process

                    popen.side_effect = launch
                    capture.side_effect = (subprocess.TimeoutExpired(["claude"], 1)
                                           if outcome == "timeout" else None)
                    capture.return_value = (output, b"Startup failed" if outcome == "exit" else b"")
                    environment = {"CLAUDE_CODE_TMPDIR": inherited,
                                   "CLAUDE_CONFIG_DIR": "/persistent/claude-auth",
                                   "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "0"}
                    with patch.dict(os.environ, environment):
                        if outcome == "success":
                            self.assertEqual(advisor.run_provider("claude", "claude-opus-5-5", "Prompt",
                                                                 Path.cwd(), native_id, 1),
                                             ("Use A.", "native-1"))
                        else:
                            with self.assertRaises(advisor.AdvisorError):
                                advisor.run_provider("claude", "claude-opus-5-5", "Prompt",
                                                     Path.cwd(), native_id, 1)
                        self.assertEqual(os.environ["CLAUDE_CODE_TMPDIR"], inherited)
                        self.assertEqual(os.environ["CLAUDE_CONFIG_DIR"], "/persistent/claude-auth")
                    popen.assert_called_once()
                    self.assertEqual(capture.call_count, 0 if outcome == "spawn" else 1)
                    self.assertEqual(len(directories), 1)
                    self.assertFalse(directories[0].exists())

    def codex_context_path(self, command):
        settings = [command[index + 1] for index, value in enumerate(command) if value == "--config"]
        files = [value.split("=", 1)[1] for value in settings if value.startswith("model_instructions_file=")]
        self.assertEqual(len(files), 1)
        path = Path(json.loads(files[0]))
        self.assertTrue(path.is_absolute())
        return path

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/codex")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_codex_preserves_large_unicode_context_and_refreshes_it_on_resume(self, capture, popen, which):
        packet = {"context": "BEGIN-CANARY\n" + "λ🧭" * 620_000 + "\nEND-CANARY"}
        first_prompt = advisor.ADVISOR_PROMPT + "\n\nContext packet:\n" + json.dumps(packet, ensure_ascii=False)
        second_prompt = first_prompt + "\nNEW-EVIDENCE-CANARY"
        self.assertGreater(len(first_prompt), 1_048_576)
        process = popen.return_value
        process.returncode = 0
        paths = []

        def capture_output(process, stdin, timeout, progress, **options):
            command = popen.call_args.args[0]
            path = self.codex_context_path(command)
            expected = first_prompt if not paths else second_prompt
            self.assertTrue(path.read_bytes() == expected.encode(), "full Unicode context must be byte-identical")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn("BEGIN-CANARY", " ".join(command))
            self.assertNotIn("END-CANARY", stdin.decode())
            self.assertLess(len(stdin), 1024)
            if paths:
                self.assertFalse(paths[0].exists())
                self.assertNotEqual(path, paths[0])
                self.assertEqual(command[command.index("resume") + 1], "native-1")
                self.assertEqual(stdin, b"Advisor consultation question:\nReconsider the new evidence.")
            else:
                self.assertNotIn("resume", command)
                self.assertTrue(stdin.strip())
            paths.append(path)
            output = [
                {"type": "thread.started", "thread_id": "native-1"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "Use A."}},
                {"type": "turn.completed"},
            ]
            return "\n".join(map(json.dumps, output)).encode(), b""

        capture.side_effect = capture_output
        self.assertEqual(advisor.run_provider("codex", "gpt-6.1-sol", first_prompt, Path.cwd(), None, 17),
                         ("Use A.", "native-1"))
        self.assertFalse(paths[0].exists())
        self.assertEqual(advisor.run_provider("codex", "gpt-6.1-sol", second_prompt, Path.cwd(), "native-1", 17,
                                             question="Reconsider the new evidence."), ("Use A.", "native-1"))
        self.assertFalse(paths[1].exists())
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(capture.call_count, 2)

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/codex")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_codex_private_context_is_removed_on_provider_failures(self, capture, popen, which):
        for failure in ("spawn", "timeout", "exit"):
            with self.subTest(failure=failure):
                popen.reset_mock()
                capture.reset_mock()
                paths = []
                process = popen.return_value
                process.returncode = 1

                def start(command, **kwargs):
                    path = self.codex_context_path(command)
                    self.assertEqual(path.read_text(), "Private full context")
                    paths.append(path)
                    if failure == "spawn":
                        raise OSError("Cannot execute")
                    return process

                popen.side_effect = start
                capture.side_effect = (subprocess.TimeoutExpired("codex", 1, stderr=b"No response")
                                       if failure == "timeout" else None)
                capture.return_value = (b"", b"Provider failed")
                with self.assertRaises(advisor.AdvisorError):
                    advisor.run_provider("codex", "gpt-6.1-sol", "Private full context", Path.cwd(), None, 1,
                                         question="Review the implementation.")
                popen.assert_called_once()
                self.assertEqual(capture.call_count, 0 if failure == "spawn" else 1)
                self.assertEqual(len(paths), 1)
                self.assertFalse(paths[0].exists())
                self.assertFalse(paths[0].parent.exists())

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen")
    def test_claude_refuses_consult_when_prompt_history_is_disabled(self, popen, which):
        for preference in ("1", "true", "yes", "on"):
            with self.subTest(preference=preference):
                with patch.dict(os.environ, {"CLAUDE_CODE_SKIP_PROMPT_HISTORY": preference}):
                    with self.assertRaisesRegex(advisor.AdvisorError, "persistence|history"):
                        advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
                    self.assertEqual(os.environ["CLAUDE_CODE_SKIP_PROMPT_HISTORY"], preference)
        popen.assert_not_called()

    @patch.object(advisor.shutil, "which", return_value=None)
    @patch.object(advisor.subprocess, "Popen")
    def test_missing_binary_does_not_attempt_fallback(self, popen, which):
        with self.assertRaises(advisor.AdvisorError):
            advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
        which.assert_called_once_with("claude")
        popen.assert_not_called()

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen", side_effect=OSError("Cannot execute"))
    def test_process_start_failure_is_reported_without_retry(self, popen, which):
        with self.assertRaises(advisor.AdvisorError):
            advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
        popen.assert_called_once()

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_nonzero_exit_is_redacted_and_does_not_fallback(self, capture, popen, which):
        secret = "sk-" + "x" * 48
        process = popen.return_value
        process.returncode = 1
        capture.return_value = (b"", f"Authentication failed: {secret}".encode())
        with self.assertRaises(advisor.AdvisorError) as raised:
            advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("exit 1", str(raised.exception))
        popen.assert_called_once()

    @patch.object(advisor.shutil, "which", return_value="/mock/bin/claude")
    @patch.object(advisor.subprocess, "Popen")
    @patch.object(advisor, "capture_process")
    def test_non_utf8_response_is_rejected_without_exposing_output(self, capture, popen, which):
        process = popen.return_value
        process.returncode = 0
        capture.return_value = (b"private output\xff", b"")
        with self.assertRaises(advisor.AdvisorError) as raised:
            advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
        self.assertNotIn("private output", str(raised.exception))

    def fake_process(self, source):
        process = subprocess.Popen([sys.executable, "-u", "-c", source],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=os.name != "nt")

        def cleanup():
            if process.poll() is None:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            process.wait(timeout=3)
            for stream in (process.stdin, process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()

        self.addCleanup(cleanup)
        return process

    def test_stream_progress_counts_activity_without_persisting_content(self):
        events = [
            {"type": "system", "subtype": "init"},
            {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "Private reasoning"}}},
            {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Private response"}}},
            {"type": "result", "subtype": "success", "result": "Use A.", "session_id": "native-1"},
        ]
        output = "\n".join(map(json.dumps, events)) + "\n"
        process = self.fake_process(
            "import sys\n"
            "assert sys.stdin.buffer.read() == b'Context packet'\n"
            f"sys.stdout.write({output!r})\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            stdout, stderr = advisor.capture_process(process, b"Context packet", 2, path)
            progress = json.loads(path.read_text())
            self.assertEqual(progress["phase"], "result_received")
            self.assertEqual(progress["thinking_events"], 1)
            self.assertEqual(progress["response_events"], 1)
            self.assertEqual(progress["output_bytes"], len(stdout))
            self.assertNotIn("Private", path.read_text())
            self.assertNotIn("Use A.", path.read_text())
            self.assertEqual(set(progress), {"phase", "provider", "thinking_events", "response_events", "output_bytes",
                                             "last_activity_seconds", "elapsed_seconds"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(stderr, b"")
        self.assertEqual(advisor.parse_response("claude", stdout.decode()), ("Use A.", "native-1"))

    def test_fake_cli_can_finish_after_a_shorter_previous_deadline(self):
        result = json.dumps({"type": "result", "result": "Use A.", "session_id": "native-1"})
        process = self.fake_process(f"import time\ntime.sleep(1.1)\nprint({result!r})\n")
        started = time.monotonic()
        stdout, _ = advisor.capture_process(process, b"", 2)
        self.assertGreater(time.monotonic() - started, 1)
        self.assertEqual(advisor.parse_response("claude", stdout.decode()), ("Use A.", "native-1"))

    def test_split_json_and_utf8_bytes_are_preserved(self):
        expected = "Résumé 🧭"
        output = (json.dumps({"type": "result", "result": expected, "session_id": "native-1"},
                             ensure_ascii=False) + "\n").encode()
        split = output.index("🧭".encode()) + 1
        process = self.fake_process(
            "import sys, time\n"
            f"sys.stdout.buffer.write({output[:split]!r}); sys.stdout.flush()\n"
            "time.sleep(0.05)\n"
            f"sys.stdout.buffer.write({output[split:]!r}); sys.stdout.flush()\n"
        )
        stdout, _ = advisor.capture_process(process, b"", 2)
        self.assertEqual(stdout, output)
        self.assertEqual(advisor.parse_response("claude", stdout.decode()), (expected, "native-1"))

    def test_early_cli_exit_closes_a_broken_prompt_pipe(self):
        process = self.fake_process("print('done')\n")
        stdout, _ = advisor.capture_process(process, b"x" * 1_048_576, 2)
        self.assertEqual(stdout, b"done\n")
        deadline = time.monotonic() + 0.5
        while not process.stdin.closed and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(process.stdin.closed)

    def test_deeply_nested_json_is_rejected_as_a_provider_error(self):
        output = "[" * 1500 + "0" + "]" * 1500
        process = self.fake_process(f"print({output!r})\n")
        stdout, _ = advisor.capture_process(process, b"", 2)
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider), self.assertRaises(advisor.AdvisorError):
                advisor.parse_response(provider, stdout.decode())

    def test_thinking_activity_does_not_extend_the_absolute_deadline(self):
        event = json.dumps({"type": "stream_event", "event": {"delta": {"type": "thinking_delta"}}})
        process = self.fake_process(
            "import time\n"
            "for _ in range(100):\n"
            f"    print({event!r}, flush=True)\n"
            "    time.sleep(0.05)\n"
        )
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired) as raised:
            advisor.capture_process(process, b"", 1)
        self.assertGreaterEqual(time.monotonic() - started, 0.9)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertGreater(raised.exception.output.count(b"thinking_delta"), 5)
        self.assertIsNotNone(process.returncode)

    def test_silent_cli_is_killed_at_the_deadline(self):
        process = self.fake_process("import time\ntime.sleep(60)\n")
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired) as raised:
            advisor.capture_process(process, b"", 1)
        self.assertEqual(raised.exception.output, b"")
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertIsNotNone(process.returncode)

    def test_stderr_flood_keeps_only_the_bounded_tail(self):
        process = self.fake_process(
            "import sys\n"
            "sys.stderr.buffer.write(b'x' * (32 * 1048576) + b' final diagnostic'); sys.stderr.flush()\n"
            "print('done')\n"
        )
        stdout, stderr = advisor.capture_process(process, b"", 5)
        self.assertEqual(stdout, b"done\n")
        self.assertEqual(len(stderr), 4096)
        self.assertTrue(stderr.endswith(b" final diagnostic"))

    def test_stdout_limit_terminates_a_flooding_cli(self):
        process = self.fake_process("import sys, time\nsys.stdout.buffer.write(b'x' * 65536); sys.stdout.flush()\ntime.sleep(60)\n")
        started = time.monotonic()
        with patch.object(advisor, "MAX_OUTPUT_BYTES", 1024):
            with self.assertRaisesRegex(advisor.AdvisorError, "output exceeded"):
                advisor.capture_process(process, b"", 2)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertIsNotNone(process.returncode)

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX process-group test")
    def test_deadline_kills_descendant_holding_pipes_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "child.pid"
            process = self.fake_process(
                "import os, time\n"
                "child = os.fork()\n"
                "if child == 0:\n"
                "    time.sleep(60)\n"
                "    os._exit(0)\n"
                f"open({str(pid_path)!r}, 'w').write(str(child))\n"
                "os._exit(0)\n"
            )
            started = time.monotonic()
            killpg = os.killpg
            try:
                with patch.object(advisor.os, "killpg", wraps=killpg) as killed:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        advisor.capture_process(process, b"", 1)
                killed.assert_called_once_with(process.pid, signal.SIGKILL)
                self.assertEqual(process.returncode, 0)
                self.assertLess(time.monotonic() - started, 2.5)
            finally:
                if pid_path.exists():
                    try:
                        os.kill(int(pid_path.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX inherited-pipe test")
    def test_escaped_pipe_holder_cannot_delay_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_path = Path(directory) / "escaped.pid"
            process = self.fake_process(
                "import os, time\n"
                "child = os.fork()\n"
                "if child == 0:\n"
                "    os.setsid()\n"
                f"    open({str(pid_path)!r}, 'w').write(str(os.getpid()))\n"
                "    time.sleep(60)\n"
                "    os._exit(0)\n"
                f"while not os.path.exists({str(pid_path)!r}): time.sleep(0.01)\n"
                "os._exit(0)\n"
            )
            started = time.monotonic()
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    advisor.capture_process(process, b"", 1)
                self.assertLess(time.monotonic() - started, 2.5)
                self.assertEqual(process.returncode, 0)
                self.assertNotEqual(os.getpgid(int(pid_path.read_text())), process.pid)
            finally:
                if pid_path.exists():
                    try:
                        os.kill(int(pid_path.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_real_cli_timeout_preserves_bounded_redacted_diagnostics(self):
        secret = "sk-" + "x" * 48
        for output in (secret.encode(), secret.encode() + b"\xf0"):
            with self.subTest(incomplete_utf8=output.endswith(b"\xf0")):
                self.check_real_cli_timeout(output, secret)

    def check_real_cli_timeout(self, output, secret):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "claude"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import sys, time\n"
                f"sys.stdout.buffer.write({output!r}); sys.stdout.flush()\n"
                f"sys.stderr.write('x' * 5000 + ' Waiting for response: ' + {secret!r}); sys.stderr.flush()\n"
                "time.sleep(60)\n"
            )
            executable.chmod(0o700)
            started = time.monotonic()
            with patch.object(advisor.shutil, "which", return_value=str(executable)):
                with self.assertRaises(advisor.AdvisorError) as raised:
                    advisor.run_provider("claude", "claude-opus-5-5", "Prompt", Path.cwd(), None, 1)
            message = str(raised.exception)
            self.assertIn("Partial stdout was captured", message)
            self.assertIn("Waiting for response", message)
            self.assertNotIn(secret, message)
            self.assertLess(len(message), 1300)
            self.assertLess(time.monotonic() - started, 5)


class ConsultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.state = self.root / "state"
        self.config = self.root / "config.json"
        self.settings = {"provider": "claude", "model": "claude-opus-5-5"}
        self.write_config()
        self.request = {
            "workspace": str(self.workspace),
            "host": "claude",
            "session_id": "host-session",
            "task_id": "task-1",
            "stage": "before_plan",
            "question": "Which approach is safer?",
            "context": "Two implementations are possible.",
        }
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("ADVISOR_ACTIVE", None)

    def write_config(self, **changes):
        self.settings.update(changes)
        self.config.write_text(json.dumps(self.settings))

    def consult(self, **changes):
        return advisor.consult(
            self.request | changes, config_path=self.config, state_dir=self.state
        )

    @patch.object(advisor, "run_provider", return_value=("Prefer approach A.", "native-1"))
    def test_identical_packet_is_cached_without_spending_budget(self, provider):
        first = self.consult()
        cached = self.consult()
        self.assertEqual(first["advice"], "Prefer approach A.")
        self.assertEqual(first["advisor_session_id"], "native-1")
        self.assertEqual(first["provider"], "claude")
        self.assertEqual(first["model"], "claude-opus-5-5")
        self.assertEqual(first["effort"], "max")
        self.assertFalse(first["identity_verified"])
        self.assertFalse(first["cached"])
        self.assertTrue(cached["cached"])
        self.assertEqual(first["remaining_consults"], 4)
        self.assertEqual(cached["remaining_consults"], 4)
        provider.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_new_packet_resumes_native_session_across_calls(self, provider):
        provider.side_effect = [("First advice", "native-1"), ("Second advice", "native-1")]
        self.consult()
        second = self.consult(stage="after_plan", context="The plan is now drafted.")
        self.assertEqual(provider.call_args_list[0].args[4], None)
        self.assertEqual(provider.call_args_list[1].args[4], "native-1")
        self.assertEqual(second["remaining_consults"], 3)

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_budget_blocks_new_packets_but_preserves_cached_answers(self, provider):
        self.write_config(max_consults_per_task=1)
        first = self.consult()
        with self.assertRaises(advisor.AdvisorError):
            self.consult(question="A different question")
        cached = self.consult()
        self.assertEqual(first["remaining_consults"], 0)
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["remaining_consults"], 0)
        provider.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_failed_provider_call_is_retryable_and_does_not_spend_budget(self, provider):
        self.write_config(max_consults_per_task=1)
        provider.side_effect = [advisor.AdvisorError("Provider failed"), ("Recovered", "native-1")]
        with self.assertRaises(advisor.AdvisorError):
            self.consult()
        result = self.consult()
        self.assertFalse(result["cached"])
        self.assertEqual(result["advice"], "Recovered")
        self.assertEqual(result["remaining_consults"], 0)
        self.assertIsNone(provider.call_args_list[1].args[4])

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_state_isolated_by_workspace_host_session_task_and_provider(self, provider):
        self.write_config(max_consults_per_task=1)
        self.consult()
        other_workspace = self.root / "other-workspace"
        other_workspace.mkdir()
        variants = [
            {"workspace": str(other_workspace)},
            {"host": "cursor"},
            {"session_id": "host-session-2"},
            {"task_id": "task-2"},
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                result = self.consult(**variant)
                self.assertFalse(result["cached"])
                self.assertIsNone(provider.call_args.args[4])
        self.write_config(provider="codex", model="gpt-6.1-sol")
        self.assertFalse(self.consult()["cached"])
        self.assertIsNone(provider.call_args.args[4])
        self.assertEqual(provider.call_count, 6)

    @patch.object(advisor, "run_provider")
    def test_obvious_secrets_are_redacted_from_prompt_result_and_state(self, provider):
        anthropic_key = "sk-ant-api03-" + "a" * 48
        openai_key = "sk-" + "b" * 48
        provider.return_value = (f"Do not use {anthropic_key} or {openai_key}.", "native-1")
        result = self.consult(
            question=f"Is {anthropic_key} configured?",
            context=f"OPENAI_API_KEY={openai_key}",
        )
        prompt = provider.call_args.args[2]
        for secret in (anthropic_key, openai_key):
            self.assertNotIn(secret, prompt)
            self.assertNotIn(secret, result["advice"])
            for path in self.state.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret.encode(), path.read_bytes())

    @patch.object(advisor, "run_provider")
    def test_recursion_guard_prevents_provider_calls(self, provider):
        os.environ["ADVISOR_ACTIVE"] = "1"
        with self.assertRaises(advisor.AdvisorError):
            self.consult()
        provider.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_rejects_invalid_requests_before_provider_call(self, provider):
        invalid = [
            {"stage": "automatic_failure"},
            {"workspace": "relative/workspace"},
            {"workspace": str(self.root / "missing")},
            {"workspace": str(self.config)},
            {"context": "x" * (1_048_576 + 1)},
            {"question": "Contains\x00control"},
        ]
        for field in self.request:
            invalid.extend([{field: ""}, {field: None}, {field: 1}])
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(advisor.AdvisorError):
                self.consult(**changes)
        for field in self.request:
            request = dict(self.request)
            del request[field]
            with self.subTest(missing=field), self.assertRaises(advisor.AdvisorError):
                advisor.consult(request, config_path=self.config, state_dir=self.state)
        provider.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_manual_external_dependency_is_rejected_before_provider_call(self, provider):
        with self.assertRaisesRegex(advisor.AdvisorError,
                                    "Advisor file paths must resolve within the consultation workspace"):
            self.consult(host="codex", dependent_paths=[str(self.root / "Tailscale.app")])
        provider.assert_not_called()
        self.assertFalse(self.state.exists())

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_manual_dependency_declarations_keep_supplied_packet_transfer(self, provider):
        for declaration in ({}, {"dependent_paths": []}, {"dependent_paths": ["src/file.py"]},
                            {"dependent_paths": [str(self.workspace / "src/file.py")]}):
            with self.subTest(declaration=declaration):
                result = self.consult(host="codex", **declaration)
                self.assertEqual(result["context_transfer"]["mode"], "supplied_packet")

    @patch.object(advisor, "run_provider")
    def test_rejects_invalid_configuration_without_calling_provider(self, provider):
        cases = [
            {},
            {"provider": "claude"},
            {"provider": "other", "model": "claude-opus-5-5"},
            {"provider": "claude", "model": ""},
            {"provider": "claude", "model": "arbitrary-model"},
            {"provider": "codex", "model": "claude-opus-5-5"},
            {"provider": "claude", "model": "claude-opus-5-5", "timeout_seconds": 0},
            {"provider": "claude", "model": "claude-opus-5-5", "max_consults_per_task": 0},
        ]
        for config in cases:
            self.config.write_text(json.dumps(config))
            with self.subTest(config=config), self.assertRaises(advisor.AdvisorError):
                self.consult()
        self.config.write_text("{invalid json")
        with self.assertRaises(advisor.AdvisorError):
            self.consult()
        self.config.unlink()
        with self.assertRaises(advisor.AdvisorError):
            self.consult()
        self.assertFalse(self.config.exists())
        provider.assert_not_called()

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_environment_configuration_paths_are_honored(self, provider):
        os.environ["ADVISOR_CONFIG"] = str(self.config)
        os.environ["ADVISOR_STATE_DIR"] = str(self.state)
        result = advisor.consult(self.request)
        self.assertEqual(result["provider"], "claude")
        self.assertTrue(self.state.is_dir())
        provider.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_unavailable_state_is_reported_before_provider_call(self, provider):
        with self.assertRaises(advisor.AdvisorError):
            advisor.consult(self.request, config_path=self.config, state_dir=self.config)
        provider.assert_not_called()

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_request_selects_default_profile_without_configuration(self, provider):
        self.config.unlink()
        profiles = {"claude": "claude-opus-5-5", "codex": "gpt-6.1-sol"}
        for name, model in profiles.items():
            with self.subTest(provider=name):
                with patch.object(advisor.configuration, "config_path", return_value=self.config), patch.dict(os.environ):
                    os.environ.pop("ADVISOR_CONFIG", None)
                    result = advisor.consult(self.request | {"provider": name}, state_dir=self.state)
                self.assertEqual(result["provider"], name)
                self.assertEqual(result["model"], model)
                self.assertEqual(provider.call_args.args[:2], (name, model))
        self.assertEqual(provider.call_count, 2)
        self.assertFalse(self.config.exists())

    @patch.object(advisor, "run_provider", return_value=("Advice", "native-1"))
    def test_request_provider_overrides_configured_provider(self, provider):
        result = self.consult(provider="codex")
        self.assertEqual(result["provider"], "codex")
        self.assertEqual(result["model"], "gpt-6.1-sol")
        self.assertEqual(provider.call_args.args[:2], ("codex", "gpt-6.1-sol"))
        provider.assert_called_once()

    @patch.object(advisor, "run_provider")
    def test_invalid_requested_provider_is_rejected_without_fallback(self, provider):
        for name in ("both", "other", "", 1):
            with self.subTest(provider=name), self.assertRaises(advisor.AdvisorError):
                self.consult(provider=name)
        provider.assert_not_called()

    @patch.object(advisor, "run_provider")
    def test_same_task_cannot_run_two_provider_calls_at_once(self, provider):
        entered = threading.Event()
        release = threading.Event()

        def blocked_provider(*args, **kwargs):
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("Test did not release the provider")
            return "Advice", "native-1"

        provider.side_effect = blocked_provider
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.consult)
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaises(advisor.AdvisorError):
                    self.consult(question="A second simultaneous question")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5)["advice"], "Advice")
        provider.assert_called_once()


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.request = {"provider": "codex", "workspace": str(self.root), "host": "zcode",
                        "session_id": "worker", "task_id": "task", "stage": "before_plan",
                        "question": "Which approach?", "context": "Synthetic context."}
        self.launch_patch = patch.object(advisor.subprocess, "Popen")
        self.launch = self.launch_patch.start()
        self.addCleanup(self.launch_patch.stop)
        self.launch.return_value.pid = os.getpid()
        self.launch.return_value.poll.return_value = None
        self.addCleanup(advisor.WORKERS.clear)
        config = self.root / "config.json"
        config.write_text("{}")
        environment = patch.dict(os.environ, {"ADVISOR_CONFIG": str(config)})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("ADVISOR_ACTIVE", None)

    def submit(self, **changes):
        return advisor.submit_consultation(self.request | changes, state_dir=self.state)

    def test_submit_returns_a_stable_job_without_waiting_for_a_provider(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual(first["status"], "pending")
        self.launch.assert_called_once()
        arguments = self.launch.call_args.args[0]
        self.assertEqual(arguments[-2:], ["worker", first["job_id"]])
        self.assertNotIn(self.request["context"], repr(arguments))
        options = self.launch.call_args.kwargs
        for stream in ("stdin", "stdout", "stderr"):
            self.assertEqual(options[stream], subprocess.DEVNULL)
        if os.name != "nt":
            self.assertTrue(options["start_new_session"])

    def test_submit_redacts_private_input_and_keeps_jobs_outside_workspace(self):
        secret = "sk-" + "x" * 48
        job = self.submit(context=f"Evidence API_KEY={secret}")
        directory = Path(job["advice_path"]).parent
        stored = (directory / "request.json").read_text()
        self.assertNotIn(secret, stored)
        self.assertIn("REDACTED", stored)
        self.assertEqual(directory.parent, self.state.resolve() / "jobs")
        if os.name != "nt":
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual((directory / "request.json").stat().st_mode & 0o777, 0o600)

    @patch.object(advisor, "consult", return_value={"advice": "Use a transaction.", "cached": False,
                       "advisor_session_id": "native-1", "provider": "codex", "model": "gpt-6.1-sol",
                       "effort": "max", "identity_verified": False, "remaining_consults": 4})
    def test_worker_persists_advice_and_result_and_never_repeats_completed_job(self, consult):
        job = self.submit()
        self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        result = advisor.read_advice(job["job_id"], state_dir=self.state)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["advice"], "Use a transaction.")
        self.assertEqual(Path(result["advice_path"]).read_text(), "Use a transaction.\n")
        self.assertFalse((Path(result["advice_path"]).parent / "request.json").exists())
        self.assertEqual(self.submit()["status"], "completed")
        self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        consult.assert_called_once()
        self.launch.assert_called_once()

    def test_worker_failure_is_redacted_and_never_relaunched(self):
        secret = "sk-" + "x" * 48
        job = self.submit()
        with patch.object(advisor, "consult", side_effect=advisor.AdvisorError(f"Provider failed {secret}")) as consult:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
            failed = self.submit()
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn(secret, failed["error"])
        consult.assert_called_once()
        self.launch.assert_called_once()

    def test_dead_worker_and_expired_job_report_interruption_without_relaunch(self):
        job = self.submit()
        self.launch.return_value.poll.return_value = 1
        self.assertEqual(self.submit()["status"], "interrupted")
        advisor.WORKERS.clear()
        directory = Path(job["advice_path"]).parent
        advisor.write_private(directory / "job.json", '{"deadline": 0}')
        self.assertEqual(self.submit()["status"], "interrupted")
        self.launch.assert_called_once()

    def test_launch_failure_is_saved_and_repeated_submit_does_not_spend(self):
        self.launch.side_effect = OSError("Cannot execute Python")
        with self.assertRaises(advisor.AdvisorError):
            self.submit()
        self.assertEqual(self.submit()["status"], "failed")
        self.launch.assert_called_once()

    def test_worker_metadata_failure_happens_before_provider_call(self):
        job = self.submit()
        write = advisor.write_private

        def fail_marker(path, text):
            if path.name == "worker.json":
                raise OSError("Cannot save worker marker")
            write(path, text)

        with patch.object(advisor, "write_private", side_effect=fail_marker):
            with patch.object(advisor, "consult") as consult:
                self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        self.assertEqual(self.submit()["status"], "failed")
        consult.assert_not_called()
        self.launch.assert_called_once()

    def test_concurrent_submit_launches_one_worker(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = list(pool.map(lambda _: self.submit(), range(4)))
        self.assertEqual(len({job["job_id"] for job in jobs}), 1)
        self.launch.assert_called_once()

    def test_job_identifiers_cannot_read_arbitrary_paths(self):
        for job_id in ("../private", "a" * 63, "/etc/passwd", None):
            with self.subTest(job_id=job_id), self.assertRaises(advisor.AdvisorError):
                advisor.read_advice(job_id, state_dir=self.state)

    def test_default_job_has_no_absolute_deadline(self):
        job = self.submit()
        metadata = json.loads((Path(job["advice_path"]).parent / "job.json").read_text())
        self.assertIsNone(metadata["deadline"])
        self.assertEqual(metadata["timeout_policy_version"], 1)

    def test_worker_uses_frozen_settings_after_user_configuration_is_deleted(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"timeout_seconds": 33, "idle_timeout_seconds": 17,
                                      "max_consults_per_task": 2, "unrelated": "do not copy"}))
        job = advisor.submit_consultation(self.request, config_path=config, state_dir=self.state)
        directory = Path(job["advice_path"]).parent
        payload = json.loads((directory / "request.json").read_text())
        self.assertNotEqual(payload["config_path"], str(config))
        frozen = Path(payload["config_path"])
        self.assertEqual(frozen.parent, directory)
        self.assertNotIn("unrelated", json.loads(frozen.read_text()))
        config.unlink()
        with patch.object(advisor, "run_provider", return_value=("Advice", "native-1")) as provider:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        self.assertEqual(provider.call_args.args[5], 33)
        self.assertEqual(provider.call_args.kwargs["idle_timeout_seconds"], 17)
        self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["remaining_consults"], 1)
        self.assertEqual(frozen.stat().st_mode & 0o777, 0o600)

    def test_deadline_free_job_with_no_worker_registration_is_interrupted(self):
        job = self.submit()
        advisor.WORKERS.clear()
        later = time.time() + 31
        with patch.object(advisor.time, "time", return_value=later):
            self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "interrupted")
        self.launch.assert_called_once()

    def test_legacy_worker_keeps_the_previous_implicit_absolute_limit(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent
        metadata = json.loads((directory / "job.json").read_text())
        metadata.pop("timeout_policy_version")
        metadata["deadline"] = time.time() + 1230
        advisor.write_private(directory / "job.json", json.dumps(metadata))
        advisor.write_private(directory / "request.json", json.dumps({"request": self.request, "config_path": None}))
        with patch.object(advisor, "run_provider", return_value=("Advice", "native-1")) as provider:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        self.assertEqual(provider.call_args.args[5], 1200)

    def test_legacy_worker_uses_historic_defaults_when_environment_config_is_missing(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent
        metadata = json.loads((directory / "job.json").read_text())
        metadata.pop("timeout_policy_version")
        metadata["deadline"] = time.time() + 1230
        advisor.write_private(directory / "job.json", json.dumps(metadata))
        advisor.write_private(directory / "request.json", json.dumps({"request": self.request, "config_path": None}))
        os.environ["ADVISOR_CONFIG"] = str(self.root / "removed-config.json")
        with patch.object(advisor, "run_provider", return_value=("Advice", "native-1")) as provider:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 0)
        self.assertEqual(provider.call_args.args[1], "gpt-6.1-sol")
        self.assertEqual(provider.call_args.args[5], 1200)
        self.assertEqual(provider.call_args.kwargs["effort"], "max")
        self.assertFalse(provider.call_args.kwargs["usage_fallback"])

    def test_legacy_worker_rejects_existing_invalid_environment_config(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent
        metadata = json.loads((directory / "job.json").read_text())
        metadata.pop("timeout_policy_version")
        metadata["deadline"] = time.time() + 1230
        advisor.write_private(directory / "job.json", json.dumps(metadata))
        advisor.write_private(directory / "request.json", json.dumps({"request": self.request, "config_path": None}))
        invalid = self.root / "invalid-config.json"
        invalid.write_text("{invalid JSON")
        os.environ["ADVISOR_CONFIG"] = str(invalid)
        with patch.object(advisor, "run_provider") as provider:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        provider.assert_not_called()
        self.assertIn("configuration as JSON", advisor.read_advice(job["job_id"], state_dir=self.state)["error"])

    def test_missing_frozen_configuration_fails_before_provider_launch(self):
        job = self.submit()
        (Path(job["advice_path"]).parent / "config.json").unlink()
        with patch.object(advisor, "run_provider") as provider:
            self.assertEqual(advisor.run_job(job["job_id"], state_dir=self.state), 1)
        self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "failed")
        provider.assert_not_called()

    def test_result_published_during_worker_poll_wins_over_interruption(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent

        def publish_result():
            advisor.write_private(directory / "result.json", json.dumps({"status": "completed", "advice": "Advice"}))
            return 0

        self.launch.return_value.poll.side_effect = publish_result
        self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "completed")
        self.launch.assert_called_once()

    def test_detached_worker_lease_ignores_reused_pid_and_expires_without_progress_updates(self):
        job = self.submit()
        directory = Path(job["advice_path"]).parent
        advisor.WORKERS.clear()
        advisor.write_private(directory / "worker.json", json.dumps({"pid": os.getpid()}))
        advisor.write_private(directory / "progress.json", json.dumps({"phase": "reasoning"}))
        with patch.object(advisor.os, "kill") as probe:
            self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "pending")
            past = time.time() - 31
            os.utime(directory / "progress.json", (past, past))
            self.assertEqual(advisor.read_advice(job["job_id"], state_dir=self.state)["status"], "interrupted")
        probe.assert_not_called()
        self.launch.assert_called_once()

    def test_background_waiter_observes_existing_job_without_exposing_advice(self):
        job = self.submit()
        job_id = job["job_id"]
        result_path = Path(job["advice_path"]).parent / "result.json"
        with patch.object(advisor.time, "sleep", side_effect=lambda _: advisor.write_private(
                result_path, json.dumps({"status": "completed", "advice": "private-advice-canary"}))) as sleep, \
                patch.object(advisor, "record_review") as receipt, \
                patch.object(advisor, "consult") as consult:
            ready = advisor.wait_for_advice(job_id, state_dir=self.state)
        self.assertEqual(ready["status"], "completed")
        self.assertEqual(ready["job_id"], job_id)
        self.assertIn("read_advice", ready["message"])
        self.assertNotIn("private-advice-canary", json.dumps(ready))
        sleep.assert_called_once_with(5)
        receipt.assert_not_called()
        consult.assert_not_called()
        self.launch.assert_called_once()

    def test_waiter_reports_terminal_status_without_a_separate_duration_limit(self):
        job = self.submit()
        job_id = job["job_id"]
        directory = Path(job["advice_path"]).parent
        advisor.write_private(directory / "result.json", json.dumps({"status": "failed", "error": "private-error-canary"}))
        self.assertEqual(advisor.wait_for_advice(job_id, state_dir=self.state)["status"], "failed")
        (directory / "result.json").unlink()
        self.launch.return_value.poll.return_value = 1
        self.assertEqual(advisor.wait_for_advice(job_id, state_dir=self.state)["status"], "interrupted")
        with patch.object(advisor, "read_advice", side_effect=[
                {"status": "pending", "poll_after_seconds": 5},
                {"status": "pending", "poll_after_seconds": 5},
                {"status": "completed"}]), \
                patch.object(advisor.time, "monotonic", side_effect=[0, 3636, 4000]), \
                patch.object(advisor.time, "sleep") as sleep:
            self.assertEqual(advisor.wait_for_advice(job_id, state_dir=self.state)["status"], "completed")
            self.assertEqual(sleep.call_count, 2)
        self.launch.assert_called_once()

    def test_watcher_command_quotes_plugin_path_and_rejects_shell_input(self):
        job_id = "a" * 64
        with patch.object(advisor, "__file__", str(self.root / "Advisor plugin/advisor.py")), \
                patch.dict(os.environ, {"ADVISOR_STATE_DIR": str(self.root / "private state")}):
            command = advisor.watcher_command(job_id)
            self.assertEqual(shlex.split(command), ["env", "ADVISOR_STATE_DIR=" + str((self.root / "private state").resolve()),
                            "uv", "run", "--script", str((self.root / "Advisor plugin/advisor.py").resolve()), "wait", job_id])
        for invalid in ("../outside", "a; touch /tmp/unwanted", None):
            with self.subTest(job_id=invalid), self.assertRaises(advisor.AdvisorError):
                advisor.watcher_command(invalid)

    def test_wait_cli_returns_readiness_only(self):
        ready = {"job_id": "a" * 64, "status": "completed", "message": "Call read_advice"}
        output = io.StringIO()
        with patch.object(sys, "argv", [str(RUNTIME), "wait", ready["job_id"]]), \
                patch.object(advisor, "wait_for_advice", return_value=ready) as wait, \
                contextlib.redirect_stdout(output):
            self.assertEqual(advisor.main(), 0)
        wait.assert_called_once_with(ready["job_id"])
        self.assertEqual(json.loads(output.getvalue()), ready)

    def test_profile_and_host_scope_produce_separate_jobs(self):
        jobs = [self.submit(), self.submit(provider="claude"), self.submit(task_id="other"),
                self.submit(session_id="other"), self.submit(host="cursor")]
        self.assertEqual(len({job["job_id"] for job in jobs}), 5)
        self.assertEqual(self.launch.call_count, 5)


if __name__ == "__main__":
    unittest.main()
