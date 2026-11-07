import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aurora_input_recovery import (InputRecovery, RecoveryDiagnostics, recovery_readiness,
                                   parse_arguments, describe_contract)
from aurora_recovery_panel import readiness_text


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.diagnostics = RecoveryDiagnostics()
        self.store = InputRecovery(Path(self.temp.name)/'inputs.json', diagnostics=self.diagnostics)
        self.addCleanup(self.store.close)
        self.identity = dict(client_id='fixture', request_id='input', message_id='message')

    def state(self, mode='durable', store=True):
        return recovery_readiness(mode, self.store if store else None, self.diagnostics,
                                  startup_mode='legacy', startup_source='default')

    def test_inspection_does_not_create_document_or_claim_write_health(self):
        state = self.state()
        self.assertTrue(state['records_available'])
        self.assertEqual(state['last_write'], 'not_observed')
        self.assertFalse(self.store.path.exists())
        self.assertEqual(state['startup_mode'], 'legacy')

    def test_legacy_closed_and_absent_are_distinct(self):
        self.assertFalse(self.state('legacy')['records_available'])
        self.assertEqual(self.state(store=False)['store_state'], 'not_open')
        self.assertIsNone(self.state(store=False)['uncertain'])
        self.store.close()
        self.assertEqual(self.state()['store_state'], 'closed')
        self.assertFalse(self.state()['records_available'])

    def test_failed_write_preserves_bytes_and_sanitizes_diagnostic(self):
        self.store.admit('private retained text', self.identity)
        before = self.store.path.read_bytes()
        with patch('aurora_input_recovery.os.replace', side_effect=PermissionError('private secret path')):
            with self.assertRaises(PermissionError): self.store.claim([self.identity])
        state = self.state()
        self.assertEqual(state['last_write'], 'failed')
        self.assertEqual(state['diagnostic']['error_type'], 'PermissionError')
        self.assertNotIn('private', json.dumps(state))
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_ack_is_idempotent_and_does_not_repair_failure(self):
        self.diagnostics.failure('delivery', OSError('hidden'))
        before = self.state()
        version = before['diagnostic']['version']
        self.assertTrue(self.diagnostics.acknowledge(version))
        self.assertFalse(self.diagnostics.acknowledge(version))
        after = self.state()
        self.assertEqual(after['last_write'], 'failed')
        self.assertEqual(after['diagnostic']['version'], version)
        self.assertTrue(after['diagnostic']['acknowledged'])
        self.assertFalse(self.store.path.exists())

    def test_new_failure_even_identical_invalidates_old_ack(self):
        self.diagnostics.failure('open', OSError())
        old = self.state()['diagnostic']['version']
        self.diagnostics.failure('open', OSError())
        with self.assertRaises(ValueError): self.diagnostics.acknowledge(old)
        self.assertFalse(self.state()['diagnostic']['acknowledged'])

    def test_restart_diagnostic_versions_cannot_cross_sessions(self):
        self.diagnostics.failure('open', ValueError())
        old = self.state()['diagnostic']['version']
        other = RecoveryDiagnostics()
        other.failure('open', ValueError())
        with self.assertRaises(ValueError): other.acknowledge(old)

    def test_successful_write_does_not_erase_prior_failure(self):
        self.diagnostics.failure('write', OSError())
        self.store.admit('held text', self.identity)
        state = self.state()
        self.assertEqual(state['last_write'], 'succeeded')
        self.assertIsNotNone(state['diagnostic'])
        self.assertFalse(state['diagnostic']['acknowledged'])

    def test_held_uncertain_and_active_counts_do_not_replay(self):
        self.store.admit('text', self.identity)
        self.store.claim([self.identity])
        self.assertEqual(self.state()['active'], 1)
        self.store.close()
        self.store = InputRecovery(self.store.path, diagnostics=self.diagnostics)
        self.addCleanup(self.store.close)
        self.assertEqual(self.state()['uncertain'], 1)
        self.assertEqual(self.state()['active'], 0)

    def test_readback_is_detached(self):
        self.diagnostics.failure('open', OSError())
        state = self.state()
        state['diagnostic']['acknowledged'] = True
        self.assertFalse(self.state()['diagnostic']['acknowledged'])

    def test_ack_failure_interleaving_does_not_ack_new_error(self):
        from concurrent.futures import ThreadPoolExecutor
        self.diagnostics.failure('write', OSError())
        old = self.state()['diagnostic']['version']
        def ack():
            try: self.diagnostics.acknowledge(old)
            except ValueError: pass
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda fn: fn(), [ack, lambda: self.diagnostics.failure('write', OSError())]))
        self.assertFalse(self.state()['diagnostic']['acknowledged'])

    def test_ui_marks_stale_and_missing_evidence_unknown(self):
        self.assertIn('unknown', readiness_text({}, True)[0])
        self.diagnostics.failure('open', ValueError())
        text, version = readiness_text(self.state(), False)
        self.assertIn('Historical', text)
        self.assertIsNone(version)
        self.assertIsNotNone(readiness_text(self.state(), True)[1])

    def test_ui_ack_does_not_remove_diagnostic_or_unknown_write(self):
        self.diagnostics.failure('open', ValueError())
        self.diagnostics.acknowledge(self.state()['diagnostic']['version'])
        text, version = readiness_text(self.state(), True)
        self.assertIn('(seen)', text)
        self.assertIn('not_observed', text)
        self.assertIsNone(version)

    def test_typed_commands_reject_extra_malformed_arguments(self):
        self.assertEqual(parse_arguments('SHOW_INPUT_RECOVERY_STATUS', []), {})
        for name, args in [('SHOW_INPUT_RECOVERY_STATUS', ['x']),
                           ('ACK_INPUT_RECOVERY_DIAGNOSTIC', []),
                           ('ACK_INPUT_RECOVERY_DIAGNOSTIC', ['bad']),
                           ('ACK_INPUT_RECOVERY_DIAGNOSTIC', ['a'*64, 'extra'])]:
            with self.assertRaises(ValueError): parse_arguments(name, args)
        self.assertEqual(describe_contract('ACK_INPUT_RECOVERY_DIAGNOSTIC')['min_arguments'], 1)


if __name__ == '__main__': unittest.main()
