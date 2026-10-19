"""Quota handoff tests use fake local CLIs; no account/model calls."""
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'plugins/advisor/advisor.py'
sys.path.insert(0, str(RUNTIME.parent))
SPEC = importlib.util.spec_from_file_location('advisor_usage_fallback_tests', RUNTIME)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class UsageFallbackTests(unittest.TestCase):
    def request(self, root, provider='claude'):
        return dict(provider=provider, workspace=str(root), host='test', session_id='worker',
                    task_id='quota-task', stage='before_task', question='Review safe handoff.',
                    context='Frozen evidence canary.')

    def test_real_fake_clis_switch_once_with_identical_context_and_saved_cause(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            os.environ.pop('CLAUDE_CODE_SKIP_PROMPT_HISTORY', None)
            root = Path(directory)
            calls = root / 'calls.jsonl'
            common = (f'#!{sys.executable}\nimport sys,json,hashlib\nfrom pathlib import Path\n'
                      f'calls=Path({str(calls)!r})\n')
            claude = root / 'claude'
            claude.write_text(common + "prompt=sys.stdin.read()\n" +
                "with calls.open('a') as f: f.write(json.dumps({'provider':'claude','hash':hashlib.sha256(prompt.encode()).hexdigest()})+'\\n')\n" +
                "print(json.dumps({'type':'result','session_id':'quota-fake','subtype':'success','is_error':True,"
                "'api_error':'usage_limit_reached','api_error_origin':'first_party','api_error_status':429,'result':'Synthetic quota refusal'}))\n"
                "sys.exit(1)\n")
            codex = root / 'codex'
            codex.write_text(common +
                "value=next(v for v in sys.argv if v.startswith('model_instructions_file='))\n"
                "prompt=Path(json.loads(value.split('=',1)[1])).read_text()\n"
                "with calls.open('a') as f: f.write(json.dumps({'provider':'codex','hash':hashlib.sha256(prompt.encode()).hexdigest()})+'\\n')\n"
                "print(json.dumps({'type':'thread.started','thread_id':'alternate-fake'}))\n"
                "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Use a bounded, explicit handoff.'}}))\n"
                "print(json.dumps({'type':'turn.completed'}))\n")
            for executable in (claude, codex):
                executable.chmod(0o700)
            config = root / 'config.json'
            config.write_text(json.dumps({'usage_fallback': True}))
            with patch.object(advisor.shutil, 'which', side_effect=lambda name: str(root / name)):
                result = advisor.consult(self.request(root), config_path=config, state_dir=root / 'state')
            invocations = [json.loads(line) for line in calls.read_text().splitlines()]
            self.assertEqual([c['provider'] for c in invocations], ['claude', 'codex'])
            self.assertEqual(invocations[0]['hash'], invocations[1]['hash'])
            self.assertEqual(result['provider'], 'codex')
            self.assertEqual(result['requested_provider'], 'claude')
            self.assertEqual([a['status'] for a in result['provider_attempts']], ['usage_exhausted', 'completed'])
            journals = list((root / 'state' / 'attempts').glob('*.json'))
            self.assertEqual(len(journals), 1)
            self.assertEqual(json.loads(journals[0].read_text()), result['provider_attempts'])

    def configured(self, root, **values):
        path = root / 'config.json'
        path.write_text(json.dumps({'usage_fallback': True, **values}))
        return path

    def quota(self):
        return advisor.UsageExhausted({'code': 'usage_limit_reached', 'evidence': 'typed_terminal',
                                      'message': 'Verified synthetic usage exhaustion.'})

    def test_config_is_explicit_boolean_and_legacy_snapshot_disables_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(advisor.frozen_job_config({}, 'claude')['usage_fallback'])
            self.assertTrue(advisor.frozen_job_config({'usage_fallback': True}, 'claude')['usage_fallback'])
            self.assertFalse(advisor.frozen_job_config({'usage_fallback': True}, 'claude', legacy=True)['usage_fallback'])
            for value in (None, 0, 1, 'true', [], {}):
                with self.subTest(value=value), self.assertRaisesRegex(advisor.AdvisorError, 'boolean'):
                    advisor.load_config(self.configured(root, usage_fallback=value))

    def test_both_directions_keep_exact_context_and_provider_memory_separate(self):
        for primary, alternate in (('claude', 'codex'), ('codex', 'claude')):
            with self.subTest(primary=primary), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
                os.environ.pop('ADVISOR_ACTIVE', None)
                root = Path(directory)
                seen = []

                def run(name, model, prompt, workspace, native, timeout, progress, **kwargs):
                    seen.append((name, model, prompt, native))
                    if name == primary:
                        raise self.quota()
                    journal = list((root / 'state' / 'attempts').glob('*.json'))[0]
                    self.assertEqual(json.loads(journal.read_text())[0]['status'], 'usage_exhausted')
                    return 'Alternate advice.', 'alternate-native'

                with patch.object(advisor, 'run_provider', side_effect=run):
                    result = advisor.consult(self.request(root, primary), config_path=self.configured(root), state_dir=root / 'state')
                self.assertEqual([row[0] for row in seen], [primary, alternate])
                self.assertEqual(seen[0][2], seen[1][2])
                self.assertEqual([row[3] for row in seen], [None, None])
                self.assertEqual(result['provider'], alternate)
                self.assertEqual(result['effort'], 'max')
                self.assertEqual(result['remaining_consults'], 4)
                counts = []
                for database in (root / 'state').glob('*/session.sqlite3'):
                    with sqlite3.connect(database) as connection:
                        exists = connection.execute("SELECT count(*) FROM sqlite_master WHERE name='consultations'").fetchone()[0]
                        counts.append(connection.execute('SELECT count(*) FROM consultations').fetchone()[0] if exists else 0)
                self.assertEqual(sorted(counts), [0, 1])

    def test_disabled_quota_and_every_other_error_never_switch(self):
        cases = [(False, self.quota()), (True, advisor.AdvisorError('429 temporary rate limit')),
                 (True, advisor.AdvisorError('Usage limit reached in quoted text')),
                 (True, advisor.AdvisorError('Authentication failed')),
                 (True, advisor.AdvisorError('Provider timed out'))]
        for enabled, error in cases:
            with self.subTest(enabled=enabled, error=error), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
                os.environ.pop('ADVISOR_ACTIVE', None)
                root = Path(directory)
                with patch.object(advisor, 'run_provider', side_effect=error) as provider:
                    with self.assertRaises(advisor.AdvisorError):
                        advisor.consult(self.request(root), config_path=self.configured(root, usage_fallback=enabled), state_dir=root / 'state')
                    self.assertEqual(provider.call_count, 1)

    def test_both_exhausted_or_alternate_failure_retains_original_cause_without_loop(self):
        for second in (self.quota(), advisor.AdvisorError('Install codex and sign in.')):
            with self.subTest(second=second), tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
                os.environ.pop('ADVISOR_ACTIVE', None)
                root = Path(directory)
                with patch.object(advisor, 'run_provider', side_effect=[self.quota(), second]) as provider:
                    with self.assertRaises(advisor.AdvisorError) as raised:
                        advisor.consult(self.request(root), config_path=self.configured(root), state_dir=root / 'state')
                    self.assertEqual(provider.call_count, 2)
                details = advisor.error_result(raised.exception)
                self.assertEqual(len(details['provider_attempts']), 2)
                self.assertEqual(details['provider_attempts'][0]['status'], 'usage_exhausted')
                self.assertEqual(details['provider_attempts'][0]['message'], 'Verified synthetic usage exhaustion.')

    def test_unwritable_handoff_journal_prevents_alternate(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            root = Path(directory)
            config = self.configured(root)
            with patch.object(advisor, 'run_provider', side_effect=self.quota()) as provider, \
                    patch.object(advisor, 'write_private', side_effect=OSError('synthetic disk failure')):
                with self.assertRaisesRegex(advisor.AdvisorError, 'persist') as raised:
                    advisor.consult(self.request(root), config_path=config, state_dir=root / 'state')
                self.assertEqual(provider.call_count, 1)
                self.assertEqual(raised.exception.provider_attempts[0]['status'], 'usage_exhausted')

    def test_absolute_deadline_is_shared_across_preflight_and_handoff(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            root = Path(directory)
            clock = [100.0]
            deadlines = []

            def run(*args, **kwargs):
                deadlines.append(kwargs['absolute_deadline'])
                if args[0] == 'claude':
                    clock[0] = 106.0
                    raise self.quota()
                self.assertEqual(clock[0], 106.0)
                return 'Within original deadline.', 'fake-native'

            with patch.object(advisor.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(advisor, 'run_provider', side_effect=run):
                advisor.consult(self.request(root), config_path=self.configured(root, timeout_seconds=10), state_dir=root / 'state')
            self.assertEqual(deadlines, [110.0, 110.0])
            clock[0] = 100.0

            def expired(*args, **kwargs):
                clock[0] = 111.0
                raise self.quota()

            with patch.object(advisor.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(advisor, 'run_provider', side_effect=expired) as provider:
                with self.assertRaisesRegex(advisor.AdvisorError, 'absolute deadline'):
                    advisor.consult(self.request(root) | {'task_id': 'expired'}, config_path=self.configured(root, timeout_seconds=10), state_dir=root / 'state')
                self.assertEqual(provider.call_count, 1)

    def test_local_consult_budget_never_triggers_alternate(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            root = Path(directory)
            config = self.configured(root, max_consults_per_task=1)
            with patch.object(advisor, 'run_provider', return_value=('Advice.', 'native-1')) as provider:
                advisor.consult(self.request(root), config_path=config, state_dir=root / 'state')
                with self.assertRaisesRegex(advisor.AdvisorError, 'Consultation limit'):
                    advisor.consult(self.request(root) | {'question': 'Another question'}, config_path=config, state_dir=root / 'state')
                self.assertEqual(provider.call_count, 1)

    def test_expired_alternate_advice_is_not_cached_or_charged(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            root = Path(directory)
            clock = [100.0]

            def run(*args, **kwargs):
                if args[0] == 'claude':
                    raise self.quota()
                clock[0] = 111.0  # Simulate final parsing crossing the total deadline.
                return 'Late advice.', 'native-late'

            with patch.object(advisor.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(advisor, 'run_provider', side_effect=run):
                with self.assertRaisesRegex(advisor.AdvisorError, 'absolute deadline') as raised:
                    advisor.consult(self.request(root), config_path=self.configured(root, timeout_seconds=10), state_dir=root / 'state')
            self.assertEqual([a['status'] for a in raised.exception.provider_attempts], ['usage_exhausted', 'failed'])
            for database in (root / 'state').glob('*/session.sqlite3'):
                with sqlite3.connect(database) as connection:
                    exists = connection.execute("SELECT count(*) FROM sqlite_master WHERE name='consultations'").fetchone()[0]
                    if exists:
                        self.assertEqual(connection.execute('SELECT count(*) FROM consultations').fetchone()[0], 0)

    def test_worker_interruption_keeps_quota_cause_and_dedup_never_relaunches(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop('ADVISOR_ACTIVE', None)
            root = Path(directory)
            config = self.configured(root)
            with patch.object(advisor.subprocess, 'Popen') as launch:
                launch.return_value.poll.return_value = None
                first = advisor.submit_consultation(self.request(root), config_path=config, state_dir=root / 'state')
                job = root / 'state' / 'jobs' / first['job_id']
                attempts = [{'provider': 'claude', 'status': 'usage_exhausted', 'message': 'Synthetic quota.'}]
                advisor.write_private(job / 'provider_attempts.json', json.dumps(attempts))
                launch.return_value.poll.return_value = 1
                interrupted = advisor.read_advice(first['job_id'], state_dir=root / 'state')
                again = advisor.submit_consultation(self.request(root), config_path=config, state_dir=root / 'state')
                self.assertEqual(interrupted['status'], 'interrupted')
                self.assertEqual(again['job_id'], first['job_id'])
                self.assertEqual(again['provider_attempts'], attempts)
                self.assertEqual(launch.call_count, 1)

    def test_failed_result_read_preserves_existing_journal_after_worker_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job_id = 'f' * 64
            job = root / 'jobs' / job_id
            job.mkdir(parents=True)
            attempts = [{'provider': 'claude', 'status': 'usage_exhausted', 'message': 'Synthetic quota.'}]
            (job / 'provider_attempts.json').write_text(json.dumps(attempts))
            (job / 'result.json').write_text(json.dumps({'status': 'failed', 'error': 'Synthetic worker error'}))
            self.assertEqual(advisor.read_advice(job_id, state_dir=root)['provider_attempts'], attempts)


if __name__ == '__main__':
    unittest.main()
