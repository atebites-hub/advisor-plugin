import importlib.util
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


RUNTIME = Path(__file__).resolve().parents[1] / "plugins/advisor/advisor.py"
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location("advisor_timeout_policy_tests", RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class TimeoutPolicyTests(unittest.TestCase):
    def fake_process(self, source):
        process = subprocess.Popen([sys.executable, "-u", "-c", source], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=os.name != "nt")

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

    @staticmethod
    def thinking(text="private-thinking-canary"):
        return json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": text}}})

    @staticmethod
    def hidden_thinking(total, delta):
        return {"type": "system", "subtype": "thinking_tokens",
                "estimated_tokens": total, "estimated_tokens_delta": delta}

    @staticmethod
    def message_start(message_id="message-hidden-1"):
        return {"type": "stream_event", "event": {
            "type": "message_start", "message": {"id": message_id}}}

    @staticmethod
    def block_start(index):
        return {"type": "stream_event", "event": {
            "type": "content_block_start", "index": index,
            "content_block": {"type": "thinking", "thinking": "private-hidden-block-canary"}}}

    def test_advancing_hidden_thinking_can_exceed_default_idle_without_persisting_content(self):
        counts = [self.hidden_thinking((index + 1) / 8, 1 / 8) for index in range(12)]
        counts += [self.hidden_thinking(10 ** 400 + index, 1) for index in range(6)]
        events = [self.message_start(), self.block_start(0), *counts]
        terminal = {"type": "result", "result": "Use A.", "session_id": "fake-hidden"}
        process = self.fake_process(
            "import json,sys,time\nsys.stdin.buffer.read()\n"
            f"for event in {events!r}:\n"
            "    print(json.dumps(event), flush=True)\n    time.sleep(0.03)\n"
            f"print(json.dumps({terminal!r}), flush=True)\n")
        clock, saved = time.monotonic, []
        started, write = clock(), advisor.write_private
        def record(path, text):
            saved.append(json.loads(text))
            write(path, text)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(advisor, "PROVIDER_CLEANUP_SECONDS", 1200), \
                patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 4000), \
                patch.object(advisor, "write_private", side_effect=record):
            path = Path(directory) / "progress.json"
            stdout, _ = advisor.capture_process(process, b"neutral input", None, path, provider="claude")
            progress = json.loads(path.read_text())
            self.assertNotIn("private-hidden-block-canary", path.read_text())
        self.assertEqual(advisor.parse_response("claude", stdout.decode()), ("Use A.", "fake-hidden"))
        self.assertGreater(progress["elapsed_seconds"], 1200)
        self.assertEqual(progress["thinking_events"], len(counts))
        self.assertTrue(any(item["phase"] == "reasoning" for item in saved))

    def test_invalid_hidden_thinking_and_diagnostics_do_not_renew_idle(self):
        valid = self.hidden_thinking(2, 1)
        cases = []
        for key in ("estimated_tokens", "estimated_tokens_delta"):
            for value in (True, False, 0, -1, float("inf"), float("-inf"), float("nan"), "2", None):
                cases.append(("stdout", valid | {key: value}, 0))
            cases.append(("stdout", {name: value for name, value in valid.items() if name != key}, 0))
        cases += [
            ("stdout", self.hidden_thinking(1, 2), 0),
            ("stdout", self.hidden_thinking(1, 1), 1),  # One initial advance; repeats are not progress.
            ("stdout", valid | {"subtype": "unknown_status"}, 0),
            ("stdout", valid | {"subtype": "api_retry"}, 0),
            ("stderr", valid, 0),
        ]
        for stream, event, maximum_events in cases:
            with self.subTest(stream=stream, event=event):
                encoded = json.dumps(event)
                process = self.fake_process(
                    "import json,sys,time\n"
                    f"print(json.dumps({self.message_start()!r}), flush=True)\n"
                    f"print(json.dumps({self.block_start(0)!r}), flush=True)\n"
                    "for _ in range(200):\n"
                    f"    print({encoded!r}, file=sys.{stream}, flush=True)\n    time.sleep(0.03)\n")
                clock = time.monotonic
                started = clock()
                with tempfile.TemporaryDirectory() as directory, \
                        patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 20):
                    path = Path(directory) / "progress.json"
                    with self.assertRaises(advisor.ProviderTimeout) as raised:
                        advisor.capture_process(process, b"", 40, path, provider="claude", idle_timeout_seconds=8)
                    self.assertLessEqual(json.loads(path.read_text())["thinking_events"], maximum_events)
                self.assertEqual(raised.exception.kind, "idle")
                self.assertLess(clock() - started, 1.5)

    def test_hidden_thinking_cannot_extend_explicit_absolute_deadline(self):
        process = self.fake_process(
            "import json,time\nfor number in range(200):\n"
            "    print(json.dumps({'type':'system','subtype':'thinking_tokens',"
            "'estimated_tokens':number+1,'estimated_tokens_delta':1}), flush=True)\n"
            "    time.sleep(0.03)\n")
        with self.assertRaises(advisor.ProviderTimeout) as raised:
            advisor.capture_process(process, b"", 0.6, provider="claude", idle_timeout_seconds=0.25)
        self.assertEqual(raised.exception.kind, "absolute")
        self.assertGreater(raised.exception.output.count(b"thinking_tokens"), 5)

    def test_hidden_thinking_resets_for_new_block_and_new_message_only(self):
        events = [self.message_start(), self.block_start(0)]
        events += [self.hidden_thinking(50 + index, 1) for index in range(4)]
        events += [self.block_start(1)]
        events += [self.hidden_thinking((index + 1) / 8, 1 / 8) for index in range(4)]
        events += [self.message_start("message-hidden-2"), self.block_start(0)]
        events += [self.hidden_thinking((index + 1) / 16, 1 / 16) for index in range(4)]
        terminal = {"type": "result", "result": "Use the new block.", "session_id": "fake-reset"}
        process = self.fake_process(
            "import json,time\n"
            f"for event in {events!r}:\n"
            "    print(json.dumps(event), flush=True)\n    time.sleep(0.06)\n"
            f"print(json.dumps({terminal!r}), flush=True)\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            stdout, _ = advisor.capture_process(process, b"", None, path,
                                                 provider="claude", idle_timeout_seconds=0.35)
            self.assertEqual(json.loads(path.read_text())["thinking_events"], 12)
        self.assertEqual(advisor.parse_response("claude", stdout.decode())[0], "Use the new block.")

    def test_replayed_message_and_block_starts_cannot_reset_hidden_thinking(self):
        for restart in (self.message_start(), self.block_start(0), self.block_start(-1), self.block_start(True)):
            with self.subTest(restart=restart):
                repeated = [restart, self.hidden_thinking(1, 1), self.hidden_thinking(2, 1)]
                process = self.fake_process(
                    "import json,time\n"
                    f"print(json.dumps({self.message_start()!r}), flush=True)\n"
                    f"print(json.dumps({self.block_start(0)!r}), flush=True)\n"
                    f"print(json.dumps({self.hidden_thinking(10, 1)!r}), flush=True)\n"
                    "for _ in range(100):\n"
                    f"    for event in {repeated!r}:\n"
                    "        print(json.dumps(event), flush=True)\n        time.sleep(0.03)\n")
                with self.assertRaises(advisor.ProviderTimeout) as raised:
                    advisor.capture_process(process, b"", 2, provider="claude", idle_timeout_seconds=0.4)
                self.assertEqual(raised.exception.kind, "idle")

    def test_alternating_message_replays_preserve_each_block_watermark(self):
        for prior_higher_block in (False, True):
            with self.subTest(prior_higher_block=prior_higher_block):
                first = [self.message_start("message-A"), self.block_start(0),
                         self.hidden_thinking(10, 1)]
                replay_a = [self.message_start("message-A"), self.block_start(0),
                            self.hidden_thinking(1, 1)]
                if prior_higher_block:
                    first += [self.block_start(2), self.hidden_thinking(1, 1)]
                    replay_a += [self.block_start(2), self.hidden_thinking(1, 1)]
                second = [self.message_start("message-B"), self.block_start(0),
                          self.hidden_thinking(1, 1)]
                process = self.fake_process(
                    "import json,time\n"
                    f"for event in {first + second!r}:\n"
                    "    print(json.dumps(event), flush=True)\n"
                    "for _ in range(200):\n"
                    f"    for event in {replay_a + second!r}:\n"
                    "        print(json.dumps(event), flush=True)\n        time.sleep(0.01)\n")
                clock = time.monotonic
                started = clock()
                with tempfile.TemporaryDirectory() as directory, \
                        patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 20):
                    path = Path(directory) / "progress.json"
                    with self.assertRaises(advisor.ProviderTimeout) as raised:
                        advisor.capture_process(process, b"", 20, path, provider="claude", idle_timeout_seconds=6)
                    self.assertEqual(raised.exception.kind, "idle")
                    self.assertEqual(json.loads(path.read_text())["thinking_events"],
                                     3 if prior_higher_block else 2)
                self.assertLess(clock() - started, 1.5)

    def test_block_start_alone_is_not_hidden_thinking_progress(self):
        process = self.fake_process(
            "import json,time\nfor index in range(100):\n"
            "    print(json.dumps({'type':'stream_event','event':{'type':'content_block_start',"
            "'index':index,'content_block':{'type':'thinking','thinking':''}}}), flush=True)\n"
            "    time.sleep(0.03)\n")
        with self.assertRaises(advisor.ProviderTimeout) as raised:
            advisor.capture_process(process, b"", 2, provider="claude", idle_timeout_seconds=0.4)
        self.assertEqual(raised.exception.kind, "idle")

    def test_fresh_and_resumed_claude_stream_hidden_thinking_with_exact_stdin(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            root = Path(directory)
            executable, log = root / "claude", root / "calls.jsonl"
            executable.write_text(f"#!{sys.executable}\n" +
                "import json,os,sys,time\nfrom pathlib import Path\n"
                "arguments=sys.argv[1:]\n"
                "native=arguments[arguments.index('--resume')+1] if '--resume' in arguments else None\n"
                "text=sys.stdin.read()\n"
                f"with Path({str(log)!r}).open('a') as stream:\n"
                "    stream.write(json.dumps({'resume':native,'stdin':text,'cwd':os.getcwd()})+'\\n')\n"
                "for number in range(17):\n"
                "    print(json.dumps({'type':'system','subtype':'thinking_tokens',"
                "'estimated_tokens':(number+1)/8,'estimated_tokens_delta':1/8}), flush=True)\n"
                "    time.sleep(0.04)\n"
                "print(json.dumps({'type':'result','subtype':'success','result':'Use A.',"
                "'session_id':'fake-resumed-hidden'}), flush=True)\n")
            executable.chmod(0o700)
            os.environ.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)
            with patch.object(advisor.shutil, "which", return_value=str(executable)):
                first = advisor.run_provider("claude", "claude-opus-5-5", "First neutral input", root, None, None,
                                             idle_timeout_seconds=0.4)
                second = advisor.run_provider("claude", "claude-opus-5-5", "Second neutral input", root, first[1], None,
                                              idle_timeout_seconds=0.4)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(first, ("Use A.", "fake-resumed-hidden"))
            self.assertEqual(second, first)
            self.assertEqual([item["resume"] for item in calls], [None, first[1]])
            self.assertEqual([item["stdin"] for item in calls], ["First neutral input", "Second neutral input"])
            self.assertNotEqual(calls[0]["cwd"], calls[1]["cwd"])

    def test_active_default_consultation_can_exceed_twenty_minutes(self):
        """A real fake CLI advances 2,000 virtual seconds while reporting progress."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "claude"
            event = json.dumps({"type": "stream_event", "event": {
                "type": "content_block_delta", "delta": {
                    "type": "thinking_delta", "thinking": "private-reasoning-canary"}}})
            result = json.dumps({"type": "result", "subtype": "success",
                                 "result": "Keep the active consultation.", "session_id": "fake-active"})
            executable.write_text(
                f"#!{sys.executable}\nimport sys, time\n"
                "sys.stdin.buffer.read()\n"
                "for _ in range(17):\n"
                f"    print({event!r}, flush=True)\n"
                "    time.sleep(0.03)\n"
                f"print({result!r}, flush=True)\n"
            )
            executable.chmod(0o700)
            request = {"provider": "claude", "workspace": str(root), "host": "test",
                       "session_id": "host", "task_id": "active", "stage": "before_plan",
                       "question": "Can active work finish?", "context": "Fake CLI only."}
            (root / "config.json").write_text("{}")
            clock = time.monotonic
            started = clock()
            with patch.dict(os.environ):
                os.environ.pop("ADVISOR_ACTIVE", None)
                os.environ.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)
                with patch.object(advisor.shutil, "which", return_value=str(executable)), \
                        patch.object(advisor, "PROVIDER_CLEANUP_SECONDS", 1200), \
                        patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 4000):
                    completed = advisor.consult(request, config_path=root / "config.json",
                                                state_dir=root / "state", progress_path=root / "progress.json")
            self.assertEqual(completed["advice"], "Keep the active consultation.")
            progress = json.loads((root / "progress.json").read_text())
            self.assertGreater(progress["elapsed_seconds"], 1200)
            self.assertNotIn("private-reasoning-canary", (root / "progress.json").read_text())

    def test_configuration_keeps_absolute_optional_and_validates_both_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with self.assertRaisesRegex(advisor.AdvisorError, "does not exist"):
                advisor.load_config(path)
            path.write_text("{}")
            self.assertNotIn("timeout_seconds", advisor.load_config(path))
            for key in ("timeout_seconds", "idle_timeout_seconds"):
                for invalid in (None, True, False, 0, -1, 3601, 1.5, "1200"):
                    with self.subTest(key=key, value=invalid):
                        path.write_text(json.dumps({key: invalid}))
                        with self.assertRaises(advisor.AdvisorError):
                            advisor.load_config(path)
                for valid in (1, 1200, 3600):
                    path.write_text(json.dumps({key: valid}))
                    self.assertEqual(advisor.load_config(path)[key], valid)

    @patch.object(advisor, "run_provider", return_value=("Use A.", "fake-config"))
    def test_consult_forwards_optional_absolute_and_configured_idle(self, provider):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop("ADVISOR_ACTIVE", None)
            root = Path(directory)
            path = root / "config.json"
            request = {"provider": "codex", "workspace": str(root), "host": "test", "session_id": "host",
                       "task_id": "defaults", "stage": "before_plan", "question": "Review", "context": "Fake."}
            path.write_text("{}")
            advisor.consult(request, config_path=path, state_dir=root / "state")
            self.assertIsNone(provider.call_args.args[5])
            self.assertEqual(provider.call_args.kwargs["idle_timeout_seconds"], 1200)
            path.write_text(json.dumps({"timeout_seconds": 7, "idle_timeout_seconds": 9}))
            advisor.consult(request | {"task_id": "explicit"}, config_path=path, state_dir=root / "state")
            self.assertEqual(provider.call_args.args[5], 7)
            self.assertEqual(provider.call_args.kwargs["idle_timeout_seconds"], 9)

    def test_changing_codex_item_text_renews_idle_without_persisting_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            source = (
                "import json, time\n"
                "for number in range(7):\n"
                "    print(json.dumps({'type':'item.updated','item':{'id':'item_0','type':'reasoning',"
                "'text':'private-codex-canary'+str(number)}}), flush=True)\n"
                "    time.sleep(0.04)\n"
                "print(json.dumps({'type':'item.completed','item':{'id':'item_1','type':'agent_message','text':'Use A.'}}))\n"
                "print(json.dumps({'type':'turn.completed'}), flush=True)\n"
            )
            process = self.fake_process(source)
            stdout, _ = advisor.capture_process(process, b"", None, path, provider="codex", idle_timeout_seconds=0.15)
            self.assertGreater(json.loads(path.read_text())["thinking_events"], 1)
            self.assertNotIn("private-codex-canary", path.read_text())
            self.assertIn(b"turn.completed", stdout)

    def test_noise_empty_and_unchanged_events_do_not_renew_idle(self):
        cases = [
            ("claude", "stderr", "diagnostic noise"),
            ("claude", "stdout", "{broken-json"),
            ("claude", "stdout", self.thinking("")),
            ("claude", "stdout", json.dumps({"type": []})),
            ("claude", "stdout", json.dumps({"type": "stream_event", "event": {
                "type": "content_block_delta", "delta": {"type": [], "thinking": "invalid"}}})),
            ("codex", "stdout", json.dumps({"type": "item.updated", "item": {
                "id": "item_0", "type": "reasoning", "text": "unchanged-private-canary"}})),
            ("codex", "stdout", json.dumps({"type": "item.updated", "item": {
                "id": "item_0", "type": "reasoning", "text": ""}})),
            ("codex", "stdout", json.dumps({"type": "item.updated", "item": {
                "id": "item_0", "type": "reasoning", "text": "\ud800"}})),
            ("codex", "stdout", json.dumps({"type": "thread.started", "thread_id": "same-thread"})),
        ]
        for provider, stream, value in cases:
            with self.subTest(provider=provider, stream=stream, value=value):
                process = self.fake_process(
                    "import sys, time\nfor _ in range(200):\n"
                    f"    print({value!r}, file=sys.{stream}, flush=True)\n"
                    "    time.sleep(0.02)\n")
                started = time.monotonic()
                with self.assertRaises(advisor.ProviderTimeout) as raised:
                    advisor.capture_process(process, b"", None, provider=provider, idle_timeout_seconds=0.15)
                self.assertEqual(raised.exception.kind, "idle")
                self.assertLess(time.monotonic() - started, 0.8)
                self.assertIsNotNone(process.returncode)

    def test_explicit_absolute_limit_wins_despite_continuous_reasoning(self):
        process = self.fake_process(
            "import time\nfor _ in range(100):\n"
            f"    print({self.thinking()!r}, flush=True)\n"
            "    time.sleep(0.02)\n")
        clock = time.monotonic
        started = clock()
        with patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 5):
            with self.assertRaises(advisor.ProviderTimeout) as raised:
                advisor.capture_process(process, b"", 1, provider="claude")
        self.assertEqual(raised.exception.kind, "absolute")
        self.assertGreater(raised.exception.output.count(b"thinking_delta"), 2)
        self.assertLess(clock() - started, 0.8)

    def test_terminal_and_eof_start_nonrenewable_cleanup(self):
        terminal = json.dumps({"type": "result", "result": "Use A.", "session_id": "fake-final"})
        cases = {
            "terminal_without_lf": f"import sys, time\nsys.stdout.write({terminal!r}); sys.stdout.flush()\ntime.sleep(60)\n",
            "terminal_then_activity": "import time\n" + f"print({terminal!r}, flush=True)\n" +
                "for _ in range(200):\n" + f"    print({self.thinking()!r}, flush=True)\n    time.sleep(0.02)\n",
            "terminal_then_hidden_thinking": "import json,time\n" + f"print({terminal!r}, flush=True)\n" +
                "for number in range(200):\n"
                "    print(json.dumps({'type':'system','subtype':'thinking_tokens',"
                "'estimated_tokens':number+1,'estimated_tokens_delta':1}), flush=True)\n"
                "    time.sleep(0.02)\n",
            "both_eof_live_process": "import os, time\nos.close(1); os.close(2)\ntime.sleep(60)\n",
            "codex_error": "import time\nprint('{\"type\":\"error\",\"message\":\"Failed\"}', flush=True)\ntime.sleep(60)\n",
        }
        for name, source in cases.items():
            with self.subTest(case=name), patch.object(advisor, "PROVIDER_CLEANUP_SECONDS", 0.15):
                process = self.fake_process(source)
                started = time.monotonic()
                with self.assertRaises(advisor.ProviderTimeout) as raised:
                    advisor.capture_process(process, b"", None, provider="codex" if name == "codex_error" else "claude",
                                             idle_timeout_seconds=1)
                self.assertEqual(raised.exception.kind, "cleanup")
                self.assertLess(time.monotonic() - started, 0.8)
                if name == "terminal_then_hidden_thinking":
                    self.assertGreater(raised.exception.output.count(b"thinking_tokens"), 2)

    def test_large_unterminated_record_is_parsed_only_when_complete(self):
        process = self.fake_process(
            "import sys\n"
            "sys.stdout.buffer.write(b'{\"type\":\"result\",\"session_id\":\"fake-large\",\"result\":\"' +"
            "b'x' * 1048576 + b'\"}')\n"
        )
        loads = advisor.json.loads
        sizes = []

        def counted(value, *args, **kwargs):
            sizes.append(len(value))
            return loads(value, *args, **kwargs)

        with patch.object(advisor.json, "loads", side_effect=counted):
            stdout, _ = advisor.capture_process(process, b"", None, provider="claude", idle_timeout_seconds=2)
        self.assertGreater(len(stdout), 1048576)
        self.assertEqual(len(sizes), 1)

    def test_silent_capture_refreshes_portable_progress_lease(self):
        class FrequentQueue(queue.Queue):
            def get(self, block=True, timeout=None):
                return super().get(block, min(timeout, 0.01) if timeout is not None else timeout)

        process = self.fake_process("import time\ntime.sleep(60)\n")
        clock = time.monotonic
        started = clock()
        saved = []
        write = advisor.write_private

        def record(path, text):
            saved.append(json.loads(text)["elapsed_seconds"])
            write(path, text)

        with tempfile.TemporaryDirectory() as directory, patch.object(advisor.queue, "Queue", FrequentQueue), \
                patch.object(advisor.time, "monotonic", side_effect=lambda: (clock() - started) * 20), \
                patch.object(advisor, "write_private", side_effect=record):
            with self.assertRaises(advisor.ProviderTimeout):
                advisor.capture_process(process, b"", 13, Path(directory) / "progress.json", provider="claude")
        self.assertGreaterEqual(len(saved), 3)
        self.assertLessEqual(max(right - left for left, right in zip(saved, saved[1:])), 5.5)

    def test_provider_timeout_diagnostics_distinguish_limits_and_redact(self):
        secret = "sk-" + "x" * 48
        terminal = json.dumps({"type": "result", "result": "private-output-canary", "session_id": "fake-final"})
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "claude"
            cases = [("absolute", 0.15, 1, None), ("idle", None, 0.15, None),
                     ("cleanup", None, 1, terminal)]
            for kind, total, idle, output in cases:
                executable.write_text(f"#!{sys.executable}\nimport sys, time\n" +
                                      f"print({secret!r}, file=sys.stderr, flush=True)\n" +
                                      (f"print({output!r}, flush=True)\n" if output else "") + "time.sleep(60)\n")
                executable.chmod(0o700)
                with self.subTest(kind=kind), patch.object(advisor.shutil, "which", return_value=str(executable)), \
                        patch.object(advisor, "PROVIDER_CLEANUP_SECONDS", 0.15), patch.dict(os.environ):
                    os.environ.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)
                    with self.assertRaises(advisor.AdvisorError) as raised:
                        advisor.run_provider("claude", "claude-opus-5-5", "Fake only", Path(directory), None, total,
                                             idle_timeout_seconds=idle)
                    message = str(raised.exception)
                    expected = {"absolute": "absolute deadline", "idle": "without valid provider progress",
                                "cleanup": "cleanup deadline"}[kind]
                    self.assertIn(expected, message)
                    self.assertNotIn(secret, message)
                    self.assertNotIn("private-output-canary", message)


if __name__ == "__main__":
    unittest.main()
