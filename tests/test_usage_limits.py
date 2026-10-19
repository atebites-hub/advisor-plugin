import copy
import datetime as dt
import json
import os
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins/advisor"))
import usage_limits


MESSAGE = "You’ve hit your usage limit. Try again later."
MODEL = "gpt-6.1-sol"


class UsageLimitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "codex"
        self.cwd = self.root / "private-invocation"
        self.home.mkdir()
        self.cwd.mkdir()
        self.started = time.time()
        self.finished = self.started + 1
        self.sid = str(uuid.UUID(int=(int(self.started * 1000) << 80) | (7 << 76) | (2 << 62) | 7))
        self.turn = "public-fixture-turn"
        date = dt.datetime.fromtimestamp(self.started, dt.timezone.utc)
        folder = self.home / "sessions" / date.strftime("%Y/%m/%d")
        folder.mkdir(parents=True)
        self.rollout = folder / f"rollout-{date:%Y-%m-%dT%H-%M-%S}-{self.sid}.jsonl"
        self.run = usage_limits.prepare_codex_usage(self.home, None, self.cwd)

    def records(self):
        stamp = dt.datetime.fromtimestamp(self.started, dt.timezone.utc).isoformat()
        payloads = [
            ("session_meta", {"id": self.sid, "timestamp": stamp, "cwd": str(self.cwd)}),
            ("event_msg", {"type": "task_started", "turn_id": self.turn,
                           "started_at": int(self.started)}),
            ("turn_context", {"turn_id": self.turn, "cwd": str(self.cwd), "model": MODEL,
                              "effort": "max"}),
            ("event_msg", {"type": "task_complete", "turn_id": self.turn,
                           "started_at": int(self.started), "completed_at": int(self.finished),
                           "last_agent_message": None,
                           "error": {"message": MESSAGE, "codex_error_info": "usage_limit_exceeded"}}),
        ]
        return [{"timestamp": stamp, "type": kind, "payload": value} for kind, value in payloads]

    def write_records(self, records=None):
        if records is None:
            records = self.records()
        self.rollout.write_text("".join(json.dumps(row) + "\n" for row in records))

    def stdout(self, message=MESSAGE):
        return "\n".join(json.dumps(row) for row in [
            {"type": "thread.started", "thread_id": self.sid},
            {"type": "turn.started"},
            {"type": "turn.failed", "error": {"message": message}},
        ]) + "\n"

    def detect(self, **kwargs):
        arguments = {"model": MODEL, "codex_run": self.run, "started_at": self.started,
                     "finished_at": self.finished}
        arguments.update(kwargs)
        return usage_limits.detect_usage("codex", self.stdout(), 1, **arguments)

    def detect_stream(self, stdout, returncode=1, **kwargs):
        arguments = {"model": MODEL, "codex_run": self.run, "started_at": self.started,
                     "finished_at": self.finished}
        arguments.update(kwargs)
        return usage_limits.detect_usage("codex", stdout, returncode, **arguments)

    def claude_stream(self, **changes):
        terminal = {"type": "result", "session_id": "public-quota-session", "subtype": "success",
                    "is_error": True, "api_error_status": 429, "api_error": "usage_limit_reached",
                    "api_error_origin": "first_party", "result": "Synthetic refusal"}
        terminal.update(changes)
        return json.dumps(terminal) + "\n"

    def detect_claude(self, stdout=None, returncode=1, **kwargs):
        return usage_limits.detect_usage("claude", stdout if stdout is not None else self.claude_stream(),
                                         returncode, model=kwargs.pop("model", "claude-opus-5-5"), **kwargs)

    def test_codex_requires_and_accepts_current_typed_terminal(self):
        self.write_records()
        result = self.detect()
        self.assertIsNotNone(result)
        self.assertEqual(result["code"], "usage_limit_exceeded")
        self.assertEqual(result["message"], MESSAGE)

    def test_claude_typed_first_party_result_with_success_subtype_is_failure(self):
        result = self.detect_claude()
        self.assertEqual(result["code"], "usage_limit_reached")
        self.assertEqual(set(result), {"code", "evidence", "message"})

    def test_claude_rejects_nonterminal_untyped_or_other_failures(self):
        for changes in ({"api_error_origin": "unknown"}, {"api_error_origin": None},
                        {"api_error": "rate_limit"}, {"api_error": "model_requires_usage_credits"},
                        {"api_error": "long_context_credits_required"}, {"api_error": None},
                        {"is_error": False}, {"is_error": 1}, {"session_id": None},
                        {"subtype": "error_max_budget_usd"}, {"subtype": "error_max_turns"},
                        {"subtype": "unknown"}, {"type": "assistant"}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.detect_claude(self.claude_stream(**changes)))

    def test_claude_rejects_replays_and_does_not_promote_warning_or_model_text(self):
        assistant = {"type": "assistant", "session_id": "public-quota-session",
                     "is_api_error_message": True, "api_error": "usage_limit_reached",
                     "api_error_origin": "first_party"}
        self.assertIsNone(self.detect_claude(json.dumps(assistant) + "\n"))
        self.assertIsNotNone(self.detect_claude(json.dumps(assistant) + "\n" + self.claude_stream()))
        assistant["session_id"] = "another-session"
        self.assertIsNone(self.detect_claude(json.dumps(assistant) + "\n" + self.claude_stream()))
        for kind in ("rate_limit_event", "assistant", "system"):
            warning = {"type": kind, "api_error": "usage_limit_reached", "api_error_origin": "first_party",
                       "is_error": True, "status": "allowed_warning", "result": self.claude_stream()}
            self.assertIsNone(self.detect_claude(json.dumps(warning) + "\n"))

    def test_both_streams_must_end_in_one_well_formed_terminal_failure(self):
        self.write_records()
        for suffix in ("garbage", "{}\n", "\n", '{"type":', self.stdout()):
            with self.subTest(suffix=suffix):
                self.assertIsNone(self.detect_stream(self.stdout() + suffix))
                self.assertIsNone(self.detect_claude(self.claude_stream() + suffix))
        for stdout in ("", "{}\n", "[]\n", '{"type":"turn.failed","error":NaN}\n'):
            self.assertIsNone(self.detect_stream(stdout))
        self.assertIsNotNone(self.detect_stream(self.stdout().rstrip("\n")))
        self.assertIsNotNone(self.detect_claude(self.claude_stream().rstrip("\n")))

    def test_normal_failed_exit_and_bound_model_are_required(self):
        self.write_records()
        for status in (-9, True, None, "1"):
            self.assertIsNone(self.detect_stream(self.stdout(), status))
            self.assertIsNone(self.detect_claude(returncode=status))
        self.assertIsNone(self.detect(model="some-other-model"))
        self.assertIsNone(self.detect_claude(model="some-other-model"))
        for started, finished in ((None, self.finished), (self.started, None),
                                  (True, self.finished), (float("nan"), self.finished),
                                  (self.finished, self.started)):
            self.assertIsNone(self.detect(started_at=started, finished_at=finished))

    def test_codex_custom_profile_requires_exact_trusted_model_and_effort(self):
        records = self.records()
        records[2]["payload"].update(model="gpt-6-astra", effort="high")
        self.write_records(records)
        self.assertIsNotNone(self.detect(model="gpt-6-astra", effort="high"))
        self.assertIsNone(self.detect(model=MODEL, effort="high"))
        self.assertIsNone(self.detect(model="gpt-6-astra", effort="max"))
        self.assertIsNone(self.detect(model="gpt-6-astra"))
        self.write_records()
        self.assertIsNone(self.detect(model="gpt-6-astra", effort="high"))

    def test_expected_profile_rejects_unsafe_or_malformed_values(self):
        self.write_records()
        for model in (None, True, [], "", "-gpt-6-astra", "gpt-6-astra --unsafe", "gpt\n6",
                      "gpt\x006", "a" * 129, "models/gpt-6-astra", "gpt:latest"):
            with self.subTest(model=model):
                self.assertIsNone(self.detect(model=model))
                self.assertIsNone(self.detect_claude(model=model))
        for effort in (None, True, [], "", "MAX", " high", "max\x00", "none", "--max"):
            with self.subTest(effort=effort):
                self.assertIsNone(self.detect(effort=effort))
                self.assertIsNone(self.detect_claude(effort=effort))

    def test_claude_custom_canonical_model_keeps_account_level_typed_proof(self):
        self.assertIsNotNone(self.detect_claude(model="claude-sonnet-4-6", effort="high"))
        self.assertIsNone(self.detect_claude(self.claude_stream(api_error_origin="unknown"),
                                           model="claude-sonnet-4-6", effort="high"))
        for model in ("opus", "gpt-6-astra", "claude-", "claude-Opus-5-5"):
            with self.subTest(model=model):
                self.assertIsNone(self.detect_claude(model=model))

    def test_nullable_required_events_cannot_hide_duplicate_native_terminals(self):
        self.write_records()
        events = [json.loads(line) for line in self.stdout().splitlines()]
        for message in (None, ''):
            bad = {'type': 'turn.failed', 'error': {'message': message}}
            self.assertIsNone(self.detect_stream('\n'.join(map(json.dumps, events[:2] + [bad] + events[2:]))))
        bad = {'type': 'turn.failed', 'error': {}}
        self.assertIsNone(self.detect_stream('\n'.join(map(json.dumps, events[:2] + [bad] + events[2:]))))
        for bad in ({'type': 'thread.started', 'thread_id': None}, {'type': 'thread.started'},
                    {'type': 'thread.started', 'thread_id': ''}):
            with self.subTest(event=bad):
                self.assertIsNone(self.detect_stream(json.dumps(bad) + '\n' + self.stdout()))

    def test_windows_positive_crash_or_interrupt_status_never_qualifies(self):
        self.write_records()
        with patch.object(usage_limits.os, 'name', 'nt'):
            for status in (0, 1, 259, 0xC0000005, 0xC000013A):
                with self.subTest(status=status):
                    self.assertIsNone(self.detect_claude(returncode=status))
                    self.assertIsNone(self.detect_stream(self.stdout(), returncode=status))
        self.assertIsNone(self.detect_claude(returncode=256))

    def test_exit_zero_can_still_report_verified_terminal_failure(self):
        self.write_records()
        self.assertIsNotNone(self.detect_stream(self.stdout(), returncode=0))
        self.assertIsNotNone(self.detect_claude(returncode=0))
        self.assertIsNone(self.detect_claude(self.claude_stream(is_error=False), returncode=0))
        success = self.stdout().replace('"turn.failed"', '"turn.completed"')
        self.assertIsNone(self.detect_stream(success, returncode=0))

    def test_codex_source_fixed_consumed_usage_templates(self):
        prefixes = [
            ("You’ve hit your usage limit.", " Try again"),
            ("You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit "
             "https://chatgpt.com/settings/usage to purchase more credits", " or try again"),
            ("You’ve hit your usage limit. Visit https://chatgpt.com/settings/usage to purchase more credits",
             " or try again"),
            ("You’ve hit your usage limit. To get more access now, send a request to your admin", " or try again"),
            ("You’ve hit your usage limit. Upgrade to Plus to continue using Codex "
             "(https://chatgpt.com/explore/plus),", " or try again"),
        ]
        messages = [prefix + suffix + ending for prefix, suffix in prefixes for ending in
                    (" later.", " at 3:07 PM.", " at Oct 18th, 2026 3:07 PM.", " at Feb 29th, 2028 12:00 AM.")]
        messages += ["Your workspace is out of credits. Add credits to continue.",
                     "Your workspace is out of credits. Ask your workspace owner to refill in order to continue."]
        for message in messages:
            with self.subTest(message=message):
                records = self.records()
                records[-1]["payload"]["error"]["message"] = message
                self.write_records(records)
                result = self.detect_stream(self.stdout(message))
                self.assertIsNotNone(result)
                self.assertEqual(result["message"], message)

    def test_codex_source_template_rejections_even_with_usage_typed_code(self):
        messages = [
            "You’ve hit your usage limit for other-model. Switch to another model now, or try again later.",
            "You’ve hit your usage limit. arbitrary promo, or try again later.",
            "To use Codex with your ChatGPT plan, upgrade to Plus: https://chatgpt.com/explore/plus.",
            "You hit your spend cap set in your workspace. Increase your spend cap to continue.",
            "You hit your spend cap set by the owner of your workspace. Ask an owner to increase your spend cap to continue.",
            "Quota exceeded. Check your plan and billing details.",
            "rate limit exceeded: slow down", "unexpected status 429 Too Many Requests: temporary throttling",
            "Authentication failed: invalid token", "Context window exceeded", MESSAGE + " (extra details)",
            " " + MESSAGE, MESSAGE + " ", MESSAGE.replace("’", "'"),
            "You’ve hit your usage limit. Try again at Oct 18st, 2026 3:07 PM.",
            "You’ve hit your usage limit. Try again at Feb 30th, 2026 3:07 PM.",
            "You’ve hit your usage limit. Try again at Feb 29th, 2027 3:07 PM.",
            "You’ve hit your usage limit. Try again at 03:07 PM.",
            "You’ve hit your usage limit. Try again at 3:60 PM.",
        ]
        for message in messages:
            with self.subTest(message=message):
                records = self.records()
                records[-1]["payload"]["error"]["message"] = message
                self.write_records(records)
                self.assertIsNone(self.detect_stream(self.stdout(message)))

    def test_codex_freeform_collision_and_missing_persistence_are_unknown(self):
        self.assertIsNone(self.detect())
        for code in ("other", "http_connection_failed", "usageLimitExceeded", None):
            records = self.records()
            records[-1]["payload"]["error"]["codex_error_info"] = code
            self.write_records(records)
            self.assertIsNone(self.detect())
        self.write_records()
        self.assertIsNone(self.detect(codex_run=None))
        changed = copy.deepcopy(self.run)
        changed["session_id"] = str(uuid.uuid4())
        self.assertIsNone(self.detect(codex_run=changed))

    def test_codex_exact_turn_cwd_model_max_and_time_binding(self):
        changes = [(0, "id", str(uuid.uuid4())), (1, "turn_id", "old-turn"),
                   (2, "turn_id", "old-turn"), (2, "cwd", str(self.root)),
                   (2, "model", "other-model"), (2, "effort", "high"),
                   (3, "turn_id", "old-turn"), (1, "started_at", int(self.started) - 100),
                   (3, "started_at", int(self.started) - 100),
                   (3, "completed_at", int(self.finished) + 100)]
        for index, key, value in changes:
            with self.subTest(index=index, key=key):
                records = self.records()
                records[index]["payload"][key] = value
                self.write_records(records)
                self.assertIsNone(self.detect())
        for index in range(4):
            records = self.records()
            records[index]["timestamp"] = "2020-01-01T00:00:00Z"
            if index == 0:
                records[index]["payload"]["timestamp"] = "2020-01-01T00:00:00Z"
            self.write_records(records)
            self.assertIsNone(self.detect())

    def test_codex_missing_ambiguous_reordered_or_torn_records_are_unknown(self):
        for index in range(4):
            records = self.records()
            records.pop(index)
            self.write_records(records)
            self.assertIsNone(self.detect())
        for index in range(4):
            records = self.records()
            records.insert(index, copy.deepcopy(records[index]))
            self.write_records(records)
            self.assertIsNone(self.detect())
        records = self.records()
        records[1], records[2] = records[2], records[1]
        self.write_records(records)
        self.assertIsNone(self.detect())
        self.write_records()
        self.rollout.write_bytes(self.rollout.read_bytes().rstrip(b"\n"))
        self.assertIsNone(self.detect())
        self.rollout.write_bytes(self.rollout.read_bytes() + b"\n{")
        self.assertIsNone(self.detect())

    def test_resume_reads_only_own_header_and_new_append_boundary(self):
        records = self.records()
        records[0]["payload"]["cwd"] = "/older-creation-directory"
        records[0]["payload"]["timestamp"] = "2020-01-01T00:00:00Z"
        self.write_records([records[0], {"type": "response_item", "payload": {"text": "old-private-body"}}])
        self.run = usage_limits.prepare_codex_usage(self.home, self.sid, self.cwd)
        self.assertIsNotNone(self.run)
        with self.rollout.open("a") as stream:
            stream.write("".join(json.dumps(row) + "\n" for row in records[1:]))
        self.assertIsNotNone(self.detect())

    def test_resume_rejects_replacement_truncation_boundary_rewrite_and_torn_prepare(self):
        for mutation in ("replace", "truncate", "rewrite"):
            with self.subTest(mutation=mutation):
                self.write_records([self.records()[0]])
                self.run = usage_limits.prepare_codex_usage(self.home, self.sid, self.cwd)
                original = self.rollout.read_bytes()
                if mutation == "replace":
                    replacement = self.rollout.with_suffix(".new")
                    replacement.write_bytes(original)
                    replacement.replace(self.rollout)
                elif mutation == "truncate":
                    self.rollout.write_bytes(b"")
                else:
                    self.rollout.write_bytes(original.replace(b'"cwd"', b'"Cwd"'))
                with self.rollout.open("ab") as stream:
                    stream.write("".join(json.dumps(row) + "\n" for row in self.records()[1:]).encode())
                self.assertIsNone(self.detect())
        self.rollout.write_bytes(b"{torn")
        self.assertIsNone(usage_limits.prepare_codex_usage(self.home, self.sid, self.cwd))

    def test_protected_bodies_are_validated_but_never_semantically_decoded(self):
        canary = 'private-body-DoNotDecode-\\-"-\u2603'
        records = self.records()
        records[0]["payload"]["instructions"] = canary
        records[2]["payload"]["developer_instructions"] = {"nested": [canary]}
        records[-1]["payload"]["last_agent_message"] = canary
        records.insert(1, {"type": "response_item", "payload": {"type": "reasoning", "text": canary}})
        records.insert(2, {"type": "event_msg", "payload": {"type": "agent_reasoning", "text": canary}})
        self.write_records(records)
        loads = json.loads

        def metadata_only(text, *args, **kwargs):
            self.assertNotIn("private-body-DoNotDecode", text)
            return loads(text, *args, **kwargs)

        with patch.object(usage_limits.json, "loads", side_effect=metadata_only):
            result = self.detect()
            self.assertIsNotNone(result)
            self.assertNotIn("private-body-DoNotDecode", repr(result))
            claude = json.dumps({"type": "assistant", "message": {"content": canary}}) + "\n"
            self.assertIsNotNone(self.detect_claude(claude + self.claude_stream()))

    def test_malformed_escapes_framing_utf8_and_duplicate_metadata_are_unknown(self):
        self.write_records()
        valid = self.rollout.read_bytes()
        for injected in (b'{"type":"response_item","payload":{"text":"bad\\q"}}\n',
                         b'{"type":"response_item","payload":{"text":"bad\\u12xz"}}\n',
                         b'{"type":"response_item","payload":{"text":"bad\x01"}}\n',
                         b'{"type":"response_item","payload":{"text":"bad\xff"}}\n',
                         b'{"type":"response_item","payload":[1,]}\n',
                         b'{"type":"response_item","payload":{"a":1,}}\n'):
            self.rollout.write_bytes(valid + injected)
            self.assertIsNone(self.detect())
        self.rollout.write_bytes(valid.replace(b'"effort": "max"', b'"effort":"max","effort":"max"'))
        self.assertIsNone(self.detect())
        self.write_records()
        escaped = self.stdout().replace('"thread_id"', '"thread_\\u0069d"')
        self.assertIsNotNone(self.detect_stream(escaped))

    def test_locator_never_opens_unrelated_files_and_rejects_ambiguous_layout(self):
        self.write_records()
        unrelated = self.rollout.parent / "rollout-unrelated-private.jsonl"
        unrelated.write_text("not-json-private-data")
        real_open = os.open

        def own_only(path, *args, **kwargs):
            self.assertNotEqual(str(path), unrelated.name)
            return real_open(path, *args, **kwargs)

        with patch.object(usage_limits.os, "open", side_effect=own_only):
            # Keep the capability identity check valid while instrumenting its implementation.
            with patch.object(usage_limits.os, "supports_dir_fd", {usage_limits.os.open}):
                self.assertIsNotNone(self.detect())
        stamp = self.rollout.name[len("rollout-"):len("rollout-") + 19]
        other_time = stamp[:-2] + ("01" if stamp[-2:] != "01" else "02")
        other_name = "rollout-" + other_time + "-" + self.sid + ".jsonl"
        (self.rollout.parent / other_name).write_bytes(self.rollout.read_bytes())
        self.assertIsNone(self.detect())

    def test_nofollow_path_identity_and_nonregular_files(self):
        self.write_records()
        actual = self.rollout.with_suffix(".actual")
        self.rollout.rename(actual)
        self.rollout.symlink_to(actual)
        self.assertIsNone(self.detect())
        self.rollout.unlink()
        os.link(actual, self.rollout)
        self.assertIsNone(self.detect())
        self.rollout.unlink()
        os.mkfifo(self.rollout)
        self.assertIsNone(self.detect())
        self.rollout.unlink()
        actual.rename(self.rollout)
        alias = self.root / "alias"
        alias.symlink_to(self.home, target_is_directory=True)
        self.assertIsNone(usage_limits.prepare_codex_usage(alias, None, self.cwd))
        changed = copy.deepcopy(self.run)
        changed["home_identity"][1] += 1
        self.assertIsNone(self.detect(codex_run=changed))

    def test_unsupported_ids_and_layouts_are_unknown(self):
        self.write_records()
        self.assertIsNone(usage_limits.prepare_codex_usage(self.home, str(uuid.uuid4()), self.cwd))
        self.assertIsNone(usage_limits.prepare_codex_usage(self.home, "../escape", self.cwd))
        self.assertIsNone(usage_limits.prepare_codex_usage(self.home, None, Path("relative")))
        renamed = self.rollout.with_name(self.rollout.stem + "_" + self.sid + ".jsonl")
        self.rollout.rename(renamed)
        self.assertIsNone(self.detect())

    def test_invalid_descriptor_missing_platform_support_and_ownership_are_unknown(self):
        self.write_records()
        for run in (None, {}, {"version": True}, {"version": 2}, {"version": 1, "home": []}):
            self.assertIsNone(self.detect(codex_run=run))
        for provider in (None, "unknown", []):
            self.assertIsNone(usage_limits.detect_usage(provider, self.stdout(), 1, model=None,
                                                       codex_run=self.run, started_at=self.started,
                                                       finished_at=self.finished))
        with patch.object(usage_limits.os, "supports_dir_fd", set()):
            self.assertIsNone(usage_limits.prepare_codex_usage(self.home, None, self.cwd))
            self.assertIsNone(self.detect())
        with patch.object(usage_limits.os, "getuid", return_value=os.getuid() + 1):
            self.assertIsNone(usage_limits.prepare_codex_usage(self.home, None, self.cwd))
            self.assertIsNone(self.detect())

    def test_codex_stream_order_success_quotes_and_duplicate_terminal_are_unknown(self):
        self.write_records()
        rows = [json.loads(line) for line in self.stdout().splitlines()]
        for changed in ([rows[1], rows[0], rows[2]], [rows[0], rows[2], rows[1]],
                        rows + [rows[-1]], [rows[0], rows[1], {"type": "turn.completed"}],
                        [rows[0], rows[1], {"type": "item.completed", "item": {
                            "type": "agent_message", "text": MESSAGE}}],
                        [rows[0], {"type": "unrecognized"}, rows[1], rows[2]]):
            stream = "".join(json.dumps(row) + "\n" for row in changed)
            self.assertIsNone(self.detect_stream(stream))

    def test_neighbor_date_locator_is_bounded_and_does_not_walk_other_dates(self):
        self.write_records()
        date = dt.datetime.fromtimestamp(self.started, dt.timezone.utc).date()
        for offset, accepted in ((-1, True), (1, True), (2, False)):
            target_date = date + dt.timedelta(days=offset)
            directory = self.home / "sessions" / target_date.strftime("%Y/%m/%d")
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / ("rollout-" + target_date.isoformat()
                                  + self.rollout.name[len("rollout-") + 10:])
            self.rollout.rename(target)
            try:
                self.assertEqual(self.detect() is not None, accepted)
            finally:
                target.rename(self.rollout)

    def test_scan_record_count_and_directory_bounds_at_limit_and_over(self):
        self.write_records()
        size = self.rollout.stat().st_size
        longest = max(len(line) for line in self.rollout.read_bytes().splitlines(keepends=True))
        for name, limit in (("MAX_SCAN_BYTES", size), ("MAX_RECORD_BYTES", longest), ("MAX_RECORDS", 4),
                            ("MAX_DIRECTORY_ENTRIES", 1)):
            with self.subTest(bound=name):
                with patch.object(usage_limits, name, limit):
                    self.assertIsNotNone(self.detect())
                with patch.object(usage_limits, name, limit - 1):
                    self.assertIsNone(self.detect())

    def test_nesting_at_limit_and_over_and_verification_deadline(self):
        self.write_records()
        original = self.rollout.read_bytes()
        for depth, accepted in ((63, True), (64, False)):
            inert = b'{"type":"response_item","payload":' + b"[" * depth + b"0" + b"]" * depth + b"}\n"
            self.rollout.write_bytes(original + inert)
            self.assertEqual(self.detect() is not None, accepted)
        self.write_records()
        self.assertIsNone(self.detect(deadline=time.monotonic() - 1))
        self.assertIsNone(usage_limits.prepare_codex_usage(self.home, None, self.cwd,
                                                         deadline=time.monotonic() - 1))
        with patch.object(usage_limits.time, "monotonic", side_effect=[0.0, 0.0, 2.0]):
            self.assertIsNone(self.detect())
        with patch.object(usage_limits.time, "monotonic", side_effect=[100.0, 100.0, 100.4]):
            self.assertIsNone(self.detect(deadline=100.25))
        with patch.object(usage_limits, "VERIFY_SECONDS", 0):
            self.assertIsNone(self.detect_claude())


if __name__ == "__main__":
    unittest.main()
