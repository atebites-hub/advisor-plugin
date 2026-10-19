import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "plugins/advisor/session_context.py"
SPEC = importlib.util.spec_from_file_location("advisor_context_tests", PATH)
context = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = context
SPEC.loader.exec_module(context)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.workspace = self.home / "workspace"
        self.workspace.mkdir()
        self.state = self.home / "state"
        root = self.home / ".zcode/cli"
        (root / "db").mkdir(parents=True)
        (root / "rollout").mkdir()
        self.database = root / "db/db.sqlite"
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE session(id TEXT PRIMARY KEY, directory TEXT)")
            db.execute("INSERT INTO session VALUES (?,?)", ("sess_fixture", str(self.workspace)))
        self.source = root / "rollout/model-io-sess_fixture.jsonl"
        self.meta = {"com.zcode/request-context": {"session_id": "sess_fixture", "turn_id": "turn_fixture", "workspace_path": str(self.workspace)}}
        self.request = {"provider": "claude", "question": "Review this change"}
        self.entry = {"type": "model_io", "sessionId": "sess_fixture", "turnId": "turn_fixture", "querySource": "main_turn", "requestId": "req_fixture",
                      "request": {"messages": [{"role": "system", "content": "Instructions"}, {"role": "tool", "content": "Tool result"}],
                                  "body": {"system": "System", "tools": [{"name": "consult_advisor", "input_schema": {"type": "object"}}]}, "headers": {"Authorization": "never-copy"}},
                      "response": {"text": "Visible assistant", "reasoningText": "hidden-response", "toolCalls": [{"id": "call_fixture", "name": "mcp__advisor__consult_advisor", "input": {"request": self.request}}]}}
        self.entry["request"]["sdkMessages"] = copy.deepcopy(self.entry["request"]["messages"])
        self.entry["request"]["body"]["messages"] = copy.deepcopy(self.entry["request"]["messages"])
        home = patch.object(context.Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("ZCODE_SESSION_DB_PATH", None)
        os.environ.pop("ZCODE_SESSION_DB", None)
        self.write(self.entry)

    def write(self, *entries):
        self.source.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    def capture(self, **kwargs):
        return context.capture_zcode_context(self.meta, self.workspace, self.state,
                    lambda text: text.replace("sk-fixture-secret", "[REDACTED]"),
                    consultation_request=self.request, **kwargs)

    def load(self, result, **changes):
        arguments = {"snapshot_id": result["context_snapshot_id"], "workspace": self.workspace,
                     "host": "zcode", "session_id": "sess_fixture", "state_dir": self.state}
        return context.load_context_snapshot(**(arguments | changes))

    def status_entry(self):
        entry = copy.deepcopy(self.entry)
        entry["request"].update(messagesKind="full", messageCount=2, messageOffset=0)
        del entry["request"]["sdkMessages"]
        del entry["request"]["body"]["messages"]
        entry["response"]["toolCalls"] = [{"id": "call_status", "name": "mcp__advisor__advisor_status", "input": {}}]
        entry["request"]["body"]["tools"] = [{"name": "advisor_status", "input_schema": {"type": "object"}}]
        return entry

    def status(self):
        return context.zcode_context_status(self.meta, self.workspace)

    def test_complete_bounded_input_cannot_start_a_native_consultation(self):
        self.entry["request"].update(messagesKind="full", messageCount=2, messageOffset=0)
        self.write(self.entry)
        with self.assertRaisesRegex(context.ContextCaptureError, "Keep complete model I/O") as captured:
            self.capture()
        self.assertNotIsInstance(captured.exception, context.ContextUnavailableError)
        self.assertIsNone(getattr(captured.exception, "scope", None))
        self.assertFalse((self.state / "contexts").exists())

    def test_unknown_recording_format_cannot_start_a_native_consultation(self):
        for mutation in ("legacy", "partial_metadata", "sdk_metadata", "body_metadata", "size_reset",
                         "missing_body_messages", "missing_request_id"):
            with self.subTest(mutation=mutation):
                entry = copy.deepcopy(self.entry)
                if mutation == "legacy":
                    del entry["request"]["sdkMessages"]
                    del entry["request"]["body"]["messages"]
                elif mutation == "partial_metadata":
                    entry["request"]["messagesKind"] = "full"
                elif mutation == "sdk_metadata":
                    entry["request"]["sdkMessagesKind"] = "tail"
                elif mutation == "body_metadata":
                    entry["request"]["bodyMessageOffset"] = 1
                elif mutation == "size_reset":
                    entry["modelIOReset"] = {"reason": "session_file_size_limit"}
                elif mutation == "missing_body_messages":
                    del entry["request"]["body"]["messages"]
                else:
                    del entry["requestId"]
                self.write(entry)
                with self.assertRaisesRegex(context.ContextCaptureError, "Keep complete model I/O") as captured:
                    self.capture()
                self.assertNotIsInstance(captured.exception, context.ContextUnavailableError)
                self.assertIsNone(getattr(captured.exception, "scope", None))
        self.assertFalse((self.state / "contexts").exists())

    def test_status_identifies_bounded_full_delta_and_tail_without_claiming_readiness(self):
        for kind, offset, count in (("full", 0, 2), ("delta", 4, 6), ("tail", 4, 6)):
            with self.subTest(kind=kind):
                entry = self.status_entry()
                entry["request"].update(messagesKind=kind, messageOffset=offset, messageCount=count)
                self.write(entry)
                result = self.status()
                self.assertEqual(result["recording_mode"], "bounded")
                self.assertFalse(result["long_session_ready"])
                self.assertEqual(result["provenance"]["request_id"], "req_fixture")
                self.assertEqual(result["counts"]["retained_messages"], 2)
                self.assertEqual(result["counts"]["message_count"], count)
                for warning in ("Desktop", "app-wide", "unbounded", "CLI"):
                    self.assertIn(warning, result["warning"])

    def test_status_requires_positive_native_full_retention_format(self):
        entry = self.status_entry()
        messages = [{"role": "user", "content": f"Message {number}"} for number in range(80)]
        entry["request"].update(messages=messages, sdkMessages=copy.deepcopy(messages))
        for key in ("messagesKind", "messageCount", "messageOffset"):
            del entry["request"][key]
        entry["request"]["body"]["messages"] = copy.deepcopy(messages)
        self.write(entry)
        result = self.status()
        self.assertEqual(result["recording_mode"], "full_retention")
        self.assertTrue(result["long_session_ready"])
        self.assertEqual(result["counts"]["retained_messages"], 80)
        self.assertEqual(result["counts"]["tool_definitions"], 1)
        self.assertEqual(result["provenance"]["turn_id"], "turn_fixture")

    def test_status_incomplete_or_mixed_native_full_format_stays_unknown(self):
        for mutation in ("missing_sdk", "empty_sdk", "malformed_sdk", "sdk_missing_role",
                         "missing_body_messages", "empty_body_messages", "malformed_body", "body_missing_role",
                         "malformed_canonical", "canonical_missing_role", "sdk_metadata", "body_metadata", "size_reset"):
            with self.subTest(mutation=mutation):
                entry = self.status_entry()
                request = entry["request"]
                for key in ("messagesKind", "messageCount", "messageOffset"):
                    del request[key]
                request["sdkMessages"] = copy.deepcopy(request["messages"])
                request["body"]["messages"] = copy.deepcopy(request["messages"])
                if mutation == "missing_sdk":
                    del request["sdkMessages"]
                elif mutation == "empty_sdk":
                    request["sdkMessages"] = []
                elif mutation == "malformed_sdk":
                    request["sdkMessages"] = [None]
                elif mutation == "sdk_missing_role":
                    request["sdkMessages"] = [{}]
                elif mutation == "missing_body_messages":
                    del request["body"]["messages"]
                elif mutation == "empty_body_messages":
                    request["body"]["messages"] = []
                elif mutation == "malformed_body":
                    request["body"]["messages"] = [None]
                elif mutation == "body_missing_role":
                    request["body"]["messages"] = [{}]
                elif mutation == "malformed_canonical":
                    request["messages"] = [None]
                elif mutation == "canonical_missing_role":
                    request["messages"] = [{}]
                elif mutation == "sdk_metadata":
                    request["sdkMessagesKind"] = "tail"
                elif mutation == "body_metadata":
                    request["bodyMessageOffset"] = 1
                else:
                    entry["modelIOReset"] = {"reason": "session_file_size_limit"}
                self.write(entry)
                result = self.status()
                self.assertEqual(result["recording_mode"], "unknown")
                self.assertFalse(result["long_session_ready"])

    def test_status_legacy_missing_and_malformed_retention_are_unknown(self):
        mutations = ("legacy", "missing_messages", "partial_metadata", "bad_count", "bad_offset",
                     "bad_kind", "full_offset", "empty_tail", "bool_count", "missing_request_id")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                entry = self.status_entry()
                request = entry["request"]
                if mutation == "legacy":
                    for key in ("messagesKind", "messageCount", "messageOffset"):
                        del request[key]
                elif mutation == "missing_messages":
                    del request["messages"]
                elif mutation == "partial_metadata":
                    del request["messageCount"]
                elif mutation == "bad_count":
                    request["messageCount"] = 3
                elif mutation == "bad_offset":
                    request["messageOffset"] = -1
                elif mutation == "bad_kind":
                    request["messagesKind"] = "other"
                elif mutation == "full_offset":
                    request.update(messageOffset=1, messageCount=3)
                elif mutation == "empty_tail":
                    request.update(messages=[], messagesKind="tail", messageOffset=2)
                elif mutation == "bool_count":
                    request["messageCount"] = True
                else:
                    del entry["requestId"]
                self.write(entry)
                self.assertEqual(self.status()["recording_mode"], "unknown")
                self.assertFalse(self.status()["long_session_ready"])

    def test_status_requires_exact_current_unique_status_invocation(self):
        for mutation in ("missing", "consultation", "duplicate", "missing_id", "unexpected_input", "other_turn", "newer_nonstatus"):
            with self.subTest(mutation=mutation):
                entry = self.status_entry()
                calls = entry["response"]["toolCalls"]
                if mutation == "missing":
                    calls.clear()
                elif mutation == "consultation":
                    calls[0]["name"] = "consult_advisor"
                elif mutation == "duplicate":
                    calls.append(copy.deepcopy(calls[0]))
                elif mutation == "missing_id":
                    del calls[0]["id"]
                elif mutation == "unexpected_input":
                    calls[0]["input"] = {"secret": "never-return-this"}
                elif mutation == "other_turn":
                    entry["turnId"] = "turn_old"
                if mutation == "newer_nonstatus":
                    later = copy.deepcopy(entry)
                    later["requestId"] = "req_later"
                    later["response"]["toolCalls"] = []
                    self.write(entry, later)
                else:
                    self.write(entry)
                result = self.status()
                self.assertEqual(result["recording_mode"], "unknown")
                self.assertNotIn("never-return-this", json.dumps(result))

    def test_status_scope_ambiguity_partial_append_and_symlink_fail_closed(self):
        entry = self.status_entry()
        self.write(entry)
        debug = self.home / ".zcode/cli/debug"
        debug.mkdir()
        other = debug / self.source.name
        other.write_bytes(self.source.read_bytes())
        self.assertEqual(self.status()["recording_mode"], "unknown")
        other.unlink()
        self.source.write_bytes(self.source.read_bytes()[:-1])
        self.assertEqual(self.status()["recording_mode"], "unknown")
        self.write(entry)
        original = self.source.with_suffix(".original")
        self.source.rename(original)
        self.source.symlink_to(original)
        self.assertEqual(self.status()["recording_mode"], "unknown")
        self.source.unlink()
        original.rename(self.source)
        for meta in ({}, {"com.zcode/request-context": {}},
                     {"com.zcode/request-context": {**self.meta["com.zcode/request-context"], "session_id": "sess_other"}}):
            with patch.object(context, "_read_file", side_effect=AssertionError("Read before scope verification")):
                self.assertEqual(context.zcode_context_status(meta, self.workspace)["recording_mode"], "unknown")
        other_workspace = self.home / "other-workspace"
        other_workspace.mkdir()
        with patch.object(context, "_read_file", side_effect=AssertionError("Read before workspace verification")):
            self.assertEqual(context.zcode_context_status(self.meta, other_workspace)["recording_mode"], "unknown")

    def test_status_reads_only_bound_session_and_never_copies_context_or_writes_state(self):
        entry = self.status_entry()
        entry["request"]["headers"] = {"Authorization": "private-header-canary"}
        entry["request"]["messages"][1]["content"] = "private-history-canary"
        entry["response"]["reasoningText"] = "private-reasoning-canary"
        self.write(entry)
        unrelated = self.source.with_name("model-io-sess_other.jsonl")
        unrelated.write_text("not a session to read")
        original = self.source.read_bytes()
        with patch.object(context, "_read_file", wraps=context._read_file) as read, \
             patch.object(context.tempfile, "NamedTemporaryFile", side_effect=AssertionError("Unexpected state write")):
            result = self.status()
        self.assertEqual(result["recording_mode"], "bounded")
        self.assertEqual([call.args[0] for call in read.call_args_list], [self.source])
        for private in ("private-header-canary", "private-history-canary", "private-reasoning-canary"):
            self.assertNotIn(private, json.dumps(result))
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.state.exists())

    def test_complete_snapshot_is_private_stable_and_excludes_credentials_and_reasoning(self):
        self.entry["request"]["body"]["tools"][0]["input_schema"]["properties"] = {"optional": {"type": ["string", "null"]}}
        self.entry["request"]["messages"].append({"role": "assistant", "content": [
            {"type": "thinking", "thinking": "hidden-block"}, {"type": "text", "text": "sk-fixture-secret"},
            {"type": "tool-result", "output": {"api_key": "unpatterned-secret", "result": "useful"}}]})
        self.write(self.entry)
        first = self.capture()
        self.assertEqual(first, self.capture())
        snapshot = self.load(first)
        serialized = json.dumps(snapshot)
        for forbidden in ("never-copy", "hidden-response", "hidden-block", "sk-fixture-secret", "unpatterned-secret"):
            self.assertNotIn(forbidden, serialized)
        self.assertIn("useful", serialized)
        self.assertIn("Visible assistant", serialized)
        self.assertEqual(snapshot["context"]["system"], "System")
        self.assertEqual(len(snapshot["context"]["tools"]), 1)
        self.assertEqual(snapshot["context"]["tools"][0]["input_schema"]["properties"]["optional"]["type"], ["string", "null"])
        self.assertEqual(first["coverage"]["semantic_model_input"], "complete")
        path = self.state / "contexts" / (first["context_snapshot_id"] + ".json")
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_reconstructible_bounded_delta_is_refused_and_later_full_request_succeeds(self):
        second = copy.deepcopy(self.entry)
        second["request"].update(messages=[{"role": "user", "content": "New input"}], messagesKind="delta", messageOffset=2, messageCount=3)
        second["requestId"] = "req_second"
        self.entry["querySource"] = "session_title"
        self.write(self.entry, second)
        with self.assertRaisesRegex(context.ContextCaptureError, "recording mode is bounded") as captured:
            self.capture()
        self.assertNotIsInstance(captured.exception, context.ContextUnavailableError)
        self.assertFalse((self.state / "contexts").exists())
        later = copy.deepcopy(self.entry)
        later.update(querySource="main_turn", requestId="req_later_full")
        later["request"]["messages"].append({"role": "user", "content": "Current full request"})
        self.write(self.entry, second, later)
        snapshot = self.load(self.capture())
        self.assertEqual(len(snapshot["context"]["messages"]), 3)
        self.assertEqual(snapshot["context"]["messages"][-1]["content"], "Current full request")
        self.assertEqual(snapshot["provenance"]["request_id"], "req_later_full")

    def test_full_recording_copies_neither_alternate_arrays_nor_native_reasoning(self):
        self.entry["request"]["messages"].append({"role": "assistant", "content": [
            {"type": "reasoning", "text": "canonical-reasoning-canary", "signature": "signature-canary"},
            {"type": "text", "text": "Visible canonical response"}]})
        self.entry["request"]["sdkMessages"].append({"role": "assistant", "content": [
            {"type": "reasoning", "text": "sdk-reasoning-canary", "signature": "sdk-signature-canary"},
            {"type": "text", "text": "sdk-only-canary"}]})
        self.entry["request"]["body"]["messages"].append({"role": "assistant", "content": [
            {"type": "thinking", "thinking": "body-thinking-canary", "signature": "body-signature-canary"},
            {"type": "text", "text": "body-only-canary"}]})
        self.write(self.entry)
        snapshot = json.dumps(self.load(self.capture()))
        self.assertIn("Visible canonical response", snapshot)
        for excluded in ("canonical-reasoning-canary", "signature-canary", "sdk-reasoning-canary",
                         "sdk-signature-canary", "sdk-only-canary", "body-thinking-canary",
                         "body-signature-canary", "body-only-canary"):
            self.assertNotIn(excluded, snapshot)

    def test_tool_schema_credential_properties_remain_while_argument_values_are_redacted(self):
        schema = {"type": "object", "properties": {"password": {"type": "string", "description": "Account password"},
                                                  "api_key": {"type": "string"}}}
        self.entry["request"]["body"]["tools"][0]["input_schema"] = schema
        self.entry["request"]["messages"][1]["content"] = {"password": "not-a-pattern", "api_key": "also-secret", "token": "short-secret"}
        self.write(self.entry)
        snapshot = self.load(self.capture())
        self.assertEqual(snapshot["context"]["tools"][0]["input_schema"], schema)
        self.assertEqual(snapshot["context"]["messages"][1]["content"], {"password": "[REDACTED]", "api_key": "[REDACTED]", "token": "[REDACTED]"})

    def test_system_in_canonical_messages_is_captured_without_native_system_field(self):
        del self.entry["request"]["body"]["system"]
        self.write(self.entry)
        snapshot = self.load(self.capture())
        self.assertEqual(snapshot["coverage"]["system_instructions"], "canonical_messages")
        self.assertEqual(snapshot["context"]["messages"][0]["content"], "Instructions")
        self.entry["request"]["messages"][0]["role"] = "user"
        self.write(self.entry)
        with self.assertRaisesRegex(context.ContextCaptureError, "system instructions"):
            self.capture()

    def test_credential_schema_literals_are_removed_without_losing_schema_shape(self):
        schema = {"type": "object", "properties": {
            "api_key": {"type": "string", "description": "Credential supplied by the user",
                        "default": "unpatterned-default", "const": "unpatterned-constant",
                        "examples": ["unpatterned-example"], "enum": ["unpatterned-enum"]},
            "mode": {"type": "string", "default": "enabled", "enum": ["enabled", "disabled"]}}}
        self.entry["request"]["body"]["tools"][0]["input_schema"] = schema
        self.write(self.entry)
        cleaned = self.load(self.capture())["context"]["tools"][0]["input_schema"]
        credential = cleaned["properties"]["api_key"]
        self.assertEqual(credential, {"type": "string", "description": "Credential supplied by the user",
                                     "default": "[REDACTED]", "const": "[REDACTED]",
                                     "examples": ["[REDACTED]"], "enum": ["[REDACTED]"]})
        self.assertEqual(cleaned["properties"]["mode"], schema["properties"]["mode"])

    def test_host_omitted_media_is_retained_as_placeholder_and_marked_incomplete(self):
        marker = "[data omitted from model-io: image/png, 4096 chars]"
        self.entry["request"]["messages"][1]["content"] = [{"type": "image", "mediaType": "image/png", "data": marker}]
        self.write(self.entry)
        snapshot = self.load(self.capture())
        self.assertEqual(snapshot["coverage"]["semantic_model_input"], "incomplete")
        self.assertEqual(snapshot["coverage"]["source_omissions"], ["binary_media"])
        self.assertIn("binary_media", snapshot["coverage"]["excluded"])
        self.assertIn(marker, json.dumps(snapshot["context"]))

    def test_missing_baseline_and_truncated_tail_fail_without_snapshot(self):
        for kind in ("delta", "tail"):
            with self.subTest(kind=kind):
                self.entry["request"].update(messagesKind=kind, messageOffset=4, messageCount=6)
                self.write(self.entry)
                with self.assertRaises(context.ContextUnavailableError) as raw:
                    context._current_record(self.source, "sess_fixture", "turn_fixture", self.request)
                self.assertIsNone(raw.exception.scope)
                with self.assertRaisesRegex(context.ContextUnavailableError, "incomplete") as captured:
                    self.capture()
                self.assertEqual(captured.exception.scope, {"workspace": str(self.workspace.resolve()),
                                 "session_id": "sess_fixture", "turn_id": "turn_fixture"})
                for detail in (f"{kind} record", "total_count=6", "offset=4", "retained_count=2",
                               "No provider job", "manual CLI", "invented IDs", "another provider",
                               "cannot repair this record", "Settings > General", "app-wide", "unbounded"):
                    self.assertIn(detail, str(captured.exception))
        self.assertFalse((self.state / "contexts").exists())

    def test_tail_does_not_reuse_old_prefix_even_when_retained_overlap_matches(self):
        baseline = copy.deepcopy(self.entry)
        baseline["request"]["messages"] = [
            {"role": "system", "content": "Old prefix"},
            {"role": "user", "content": "Retained request"},
            {"role": "tool", "content": "Retained result"},
        ]
        full_current = [
            {"role": "system", "content": "Changed omitted prefix"},
            *baseline["request"]["messages"][1:],
            {"role": "user", "content": "New request"},
        ]
        tail = copy.deepcopy(self.entry)
        tail["requestId"] = "req_tail"
        tail["request"].update(messages=full_current[1:], messagesKind="tail", messageOffset=1, messageCount=4)
        self.assertEqual(tail["request"]["messages"][:2], baseline["request"]["messages"][1:])
        self.write(baseline, tail)
        with self.assertRaisesRegex(context.ContextUnavailableError, "tail record.*no older prefix"):
            self.capture()
        self.assertFalse((self.state / "contexts").exists())

    def test_full_retention_log_larger_than_source_window_selects_current_complete_record(self):
        entries = [copy.deepcopy(self.entry) for _ in range(8)]
        for number, entry in enumerate(entries):
            entry["requestId"] = f"req_full_{number}"
        entries[-1]["request"]["messages"][1]["content"] = "Current full-record canary"
        self.write(*entries)
        window = len(json.dumps(entries[-1]).encode()) * 3
        self.assertGreater(self.source.stat().st_size, window)
        with patch.object(context, "MAX_SOURCE_BYTES", window):
            result = self.capture()
        snapshot = self.load(result)
        self.assertEqual(snapshot["provenance"]["request_id"], "req_full_7")
        self.assertEqual(snapshot["context"]["messages"][1]["content"], "Current full-record canary")
        self.assertEqual(snapshot["coverage"]["semantic_model_input"], "complete")
        path = self.state / "contexts" / (result["context_snapshot_id"] + ".json")
        self.assertLess(path.stat().st_size, context.MAX_CONTEXT_BYTES)

    def test_incomplete_input_does_not_grant_scope_to_unverified_calls(self):
        tail = copy.deepcopy(self.entry)
        tail["request"].update(messagesKind="tail", messageOffset=4, messageCount=6)
        cases = []
        for mutation in ("missing", "different_request", "duplicate", "missing_id", "empty_id", "concurrent_edit", "invalid_retention"):
            entry = copy.deepcopy(tail)
            calls = entry["response"]["toolCalls"]
            if mutation == "missing":
                calls.clear()
            elif mutation == "different_request":
                calls[0]["input"]["request"]["question"] = "A different current invocation"
            elif mutation == "duplicate":
                calls.append(copy.deepcopy(calls[0]))
            elif mutation == "missing_id":
                del calls[0]["id"]
            elif mutation == "empty_id":
                calls[0]["id"] = ""
            elif mutation == "concurrent_edit":
                calls.append({"id": "write", "name": "Write", "input": {"file_path": "cache.py"}})
            elif mutation == "invalid_retention":
                entry["request"]["messageCount"] = 7
            cases.append((mutation, entry))
        for mutation, entry in cases:
            with self.subTest(mutation=mutation):
                self.write(entry)
                with patch.object(context.time, "monotonic", side_effect=[0, 3]):
                    with self.assertRaises(context.ContextCaptureError) as captured:
                        self.capture()
                self.assertNotIsInstance(captured.exception, context.ContextUnavailableError)
                self.assertIsNone(getattr(captured.exception, "scope", None))
                if mutation == "concurrent_edit":
                    self.assertIn("separate tool batch", str(captured.exception))
        self.assertFalse((self.state / "contexts").exists())

    def test_unavailable_context_scope_requires_verified_workspace_and_unique_source(self):
        complete = copy.deepcopy(self.entry)
        self.entry["request"].update(messagesKind="tail", messageOffset=4, messageCount=6)
        self.write(self.entry)
        with self.assertRaises(context.ContextCaptureError) as wrong_workspace:
            context.capture_zcode_context(self.meta, self.home, self.state, str, consultation_request=self.request)
        self.assertIsNone(getattr(wrong_workspace.exception, "scope", None))
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE session SET directory = ?", (str(self.home),))
        with self.assertRaises(context.ContextCaptureError) as wrong_session:
            self.capture()
        self.assertIsNone(getattr(wrong_session.exception, "scope", None))
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE session SET directory = ?", (str(self.workspace),))
        debug = self.home / ".zcode/cli/debug"
        debug.mkdir()
        (debug / self.source.name).write_text(json.dumps(complete) + "\n")
        with self.assertRaisesRegex(context.ContextCaptureError, "Multiple current") as ambiguous:
            self.capture()
        self.assertIsNone(getattr(ambiguous.exception, "scope", None))

    def test_native_metadata_and_workspace_binding_are_required(self):
        for key in ("session_id", "turn_id", "workspace_path"):
            meta = copy.deepcopy(self.meta)
            del meta["com.zcode/request-context"][key]
            with self.subTest(key=key), self.assertRaises(context.ContextCaptureError):
                context.capture_zcode_context(meta, self.workspace, self.state, str)
        with self.assertRaises(context.ContextCaptureError):
            context.capture_zcode_context({"sessionId": "sess_fixture"}, self.workspace, self.state, str)
        with self.assertRaises(context.ContextCaptureError):
            context.capture_zcode_context(self.meta, self.home, self.state, str)
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE session SET directory = ?", (str(self.home),))
        with self.assertRaises(context.ContextCaptureError):
            self.capture()

    def test_nested_native_cwd_keeps_the_indexed_workspace_for_status_and_capture(self):
        child = self.workspace / "src" / "nested"
        child.mkdir(parents=True)
        self.meta["com.zcode/request-context"]["workspace_path"] = str(child)
        captured = self.capture()
        self.assertEqual(captured["workspace"], str(self.workspace.resolve()))
        self.assertEqual(self.load(captured)["binding"]["workspace"], str(self.workspace.resolve()))
        implicit = context.capture_zcode_context(self.meta, None, self.state, str,
                                                 consultation_request=self.request)
        self.assertEqual(implicit["workspace"], str(self.workspace.resolve()))

        entry = self.status_entry()
        for key in ("messagesKind", "messageCount", "messageOffset"):
            del entry["request"][key]
        entry["request"]["sdkMessages"] = copy.deepcopy(entry["request"]["messages"])
        entry["request"]["body"]["messages"] = copy.deepcopy(entry["request"]["messages"])
        self.write(entry)
        self.assertEqual(self.status()["recording_mode"], "full_retention")
        alias = self.home / "cwd-alias"
        alias.symlink_to(child, target_is_directory=True)
        self.meta["com.zcode/request-context"]["workspace_path"] = str(alias)
        self.assertEqual(context.zcode_context_status(self.meta)["recording_mode"], "full_retention")

    def test_cwd_root_resolution_rejects_outside_paths_and_requested_subdirectories(self):
        child = self.workspace / "src"
        child.mkdir()
        outside = self.home / "other-workspace"
        outside.mkdir()
        escape = self.workspace / "escape"
        escape.symlink_to(outside, target_is_directory=True)
        for cwd in (outside, self.home, escape, Path("src")):
            meta = copy.deepcopy(self.meta)
            meta["com.zcode/request-context"]["workspace_path"] = str(cwd)
            with self.subTest(cwd=cwd), patch.object(context, "_read_file", side_effect=AssertionError("Read before ownership verification")):
                self.assertEqual(context.zcode_context_status(meta, self.workspace)["recording_mode"], "unknown")
                with self.assertRaises(context.ContextCaptureError):
                    context.capture_zcode_context(meta, self.workspace, self.state, str,
                                                  consultation_request=self.request)
        self.meta["com.zcode/request-context"]["workspace_path"] = str(child)
        with self.assertRaises(context.ContextCaptureError):
            context.capture_zcode_context(self.meta, child, self.state, str,
                                          consultation_request=self.request)
        self.assertFalse((self.state / "contexts").exists())

    def test_foreign_session_and_duplicate_invocation_are_rejected(self):
        self.entry["sessionId"] = "sess_other"
        self.write(self.entry)
        with self.assertRaises(context.ContextCaptureError):
            self.capture()
        self.entry["sessionId"] = "sess_fixture"
        self.entry["response"]["toolCalls"] *= 2
        self.write(self.entry)
        with self.assertRaisesRegex(context.ContextCaptureError, "unambiguously"):
            self.capture()

    def test_distinct_consultations_in_one_batch_have_stable_call_bound_snapshots(self):
        self.request["dependent_paths"] = ["shared_requests.py"]
        second_request = {**self.request, "question": "Review the cancellation cleanup path"}
        self.entry["response"]["toolCalls"].append({
            "id": "call_second", "name": "mcp__advisor__consult_advisor", "input": {"request": second_request}})
        self.write(self.entry)
        first = self.capture()
        second = context.capture_zcode_context(self.meta, self.workspace, self.state, str,
                                               consultation_request=second_request)
        self.assertNotEqual(first["context_snapshot_id"], second["context_snapshot_id"])
        self.assertEqual(first["context_snapshot_id"], self.capture()["context_snapshot_id"])
        repeated = context.capture_zcode_context(self.meta, self.workspace, self.state, str,
                                                 consultation_request=second_request)
        self.assertEqual(second["context_snapshot_id"], repeated["context_snapshot_id"])
        self.assertEqual(first["provenance"]["tool_call_id"], "call_fixture")
        self.assertEqual(second["provenance"]["tool_call_id"], "call_second")
        self.assertEqual(self.load(first)["provenance"]["tool_call_id"], "call_fixture")
        self.assertEqual(self.load(second)["provenance"]["tool_call_id"], "call_second")
        self.assertEqual(first["coverage"], second["coverage"])
        self.assertEqual(self.load(first)["context"], self.load(second)["context"])

    def test_review_cannot_race_a_file_edit_in_the_same_tool_batch(self):
        self.entry["response"]["toolCalls"].append({"id": "write", "name": "Write", "input": {"file_path": "cache.py"}})
        self.write(self.entry)
        with self.assertRaisesRegex(context.ContextCaptureError, "separate tool batch"):
            self.capture()

    def test_changed_invocation_does_not_reuse_previous_matching_request(self):
        later = copy.deepcopy(self.entry)
        later["response"]["toolCalls"][0]["input"]["request"]["question"] = "Different question"
        self.write(self.entry, later)
        with patch.object(context.time, "monotonic", side_effect=[0, 3]):
            with self.assertRaisesRegex(context.ContextCaptureError, "older request"):
                self.capture()

    def test_partial_append_waits_for_complete_current_record(self):
        complete = self.source.read_bytes()
        self.source.write_bytes(complete[:-2])
        writer = threading.Thread(target=lambda: (time.sleep(0.1), self.source.write_bytes(complete)))
        writer.start()
        try:
            self.assertEqual(self.capture()["session_id"], "sess_fixture")
        finally:
            writer.join()

    def test_size_limit_does_not_truncate_or_persist(self):
        with self.assertRaisesRegex(context.ContextCaptureError, "limit"):
            self.capture(max_bytes=50)
        self.assertFalse((self.state / "contexts").exists())

    def test_snapshot_hash_and_scope_are_verified(self):
        result = self.capture()
        for changes in ({"workspace": self.home}, {"session_id": "sess_other"}, {"host": "claude"}):
            with self.subTest(changes=changes), self.assertRaises(context.ContextCaptureError):
                self.load(result, **changes)
        path = self.state / "contexts" / (result["context_snapshot_id"] + ".json")
        path.write_text('{}')
        with self.assertRaisesRegex(context.ContextCaptureError, "integrity"):
            self.load(result)

    @unittest.skipIf(os.name == "nt", "POSIX symlink protection")
    def test_source_and_snapshot_symlinks_are_refused(self):
        original = self.source.with_suffix(".original")
        self.source.rename(original)
        self.source.symlink_to(original)
        with self.assertRaises(context.ContextCaptureError):
            self.capture()
        self.source.unlink()
        original.rename(self.source)
        result = self.capture()
        path = self.state / "contexts" / (result["context_snapshot_id"] + ".json")
        moved = path.with_suffix(".original")
        path.rename(moved)
        path.symlink_to(moved)
        with self.assertRaises(context.ContextCaptureError):
            self.load(result)


if __name__ == "__main__":
    unittest.main()
