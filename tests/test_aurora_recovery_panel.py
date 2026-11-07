import json
from pathlib import Path
import tempfile
import unittest

from aurora_input_recovery import InputRecovery, RESULT_SCHEMA
from aurora_recovery_panel import (RecoveryReceiptClient, recovery_actions, recovery_command,
                                   recovery_page)


class RecoveryPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = InputRecovery(self.root/'state.json')
        self.identity = dict(client_id='client', request_id='input', message_id='message')
        self.store.admit('Exact message ; "text"', self.identity)
        self.row = self.store.snapshot()['entries'][0]
        self.record = dict(client_id='panel', request_id='command', message_id='command-message')
        self.calls = []
        self.now = 0
        self.client = RecoveryReceiptClient(self.root, self.send, clock=lambda:self.now)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def send(self, command):
        self.calls.append(command)
        return self.record

    def receipt(self):
        return dict(self.record, event='command_result', terminal=True, memory_command_results=[
            dict(schema_version=RESULT_SCHEMA, command='SHOW_INPUT_RECOVERY',success=True,readback=self.store.snapshot(0,10))])

    def append(self, record, *, newline=True, file='command_log'):
        with self.client.paths[file].open('a',encoding='utf-8') as target:
            target.write(json.dumps(record)+('\n' if newline else ''))

    def test_exact_page_preserves_text_and_correlation(self):
        page = recovery_page(self.receipt())
        self.assertEqual(page['entries'][0]['text'], self.row['text'])
        page['entries'][0]['text'] = 'changed'
        self.assertNotEqual(self.store.snapshot()['entries'][0]['text'],'changed')

    def test_rejects_failed_malformed_or_unbounded_readback(self):
        for mutate in (lambda r:r['memory_command_results'][0].update(success=False),
                       lambda r:r['memory_command_results'][0]['readback'].update(omitted=100),
                       lambda r:r['memory_command_results'][0]['readback']['entries'][0].update(version='bad'),
                       lambda r:r['memory_command_results'][0]['readback'].update(entries=[self.row]*11)):
            receipt=self.receipt(); mutate(receipt)
            with self.assertRaises(ValueError): recovery_page(receipt)

    def test_actions_distinguish_queued_active_uncertain_and_responded(self):
        self.assertEqual(recovery_actions(self.row),dict(cancel=True,retry=False,acknowledgement=False))
        self.assertFalse(recovery_actions(dict(self.row,phase='submitted'))['cancel'])
        self.assertFalse(recovery_actions(dict(self.row,phase='responded'))['retry'])
        self.assertTrue(recovery_actions(dict(self.row,phase='held'))['retry'])
        self.assertTrue(recovery_actions(dict(self.row,phase='uncertain'))['acknowledgement'])
        self.assertTrue(recovery_actions(dict(self.row,phase='cancelled',request_started=True))['acknowledgement'])
        self.assertFalse(recovery_actions(None)['retry'])

    def test_commands_use_version_and_explicit_acknowledgement(self):
        self.assertTrue(recovery_command('RETRY_INPUT',self.row,True).endswith(',allow_uncertain)'))
        self.assertNotIn('allow_uncertain',recovery_command('CANCEL_QUEUED_INPUT',self.row))
        with self.assertRaises(ValueError): recovery_command('RETRY_INPUT',dict(self.row,version='not-a-version'))

    def test_cursor_ignores_unrelated_receipts_and_waits_for_newline(self):
        self.append(self.receipt())  # Old receipt precedes this submission.
        self.client.start('SHOW_INPUT_RECOVERY(0,10)')
        self.assertIsNone(self.client.poll())
        for field in ('message_id','request_id','client_id'):
            self.append(dict(self.receipt(),**{field:'unrelated'}))
        self.assertIsNone(self.client.poll())
        self.append(self.receipt(),newline=False)
        self.assertIsNone(self.client.poll())
        with self.client.paths['command_log'].open('a') as target: target.write('\n')
        self.assertEqual(self.client.poll()['request_id'],self.record['request_id'])
        self.assertIsNone(self.client.pending)

    def test_timeout_does_not_retry_or_accept_ingestion_as_completion(self):
        self.client.start('RETRY_INPUT(fixture)')
        self.append(dict(self.record,event='message_ingested'),file='bridge_log')
        self.assertIsNone(self.client.poll())
        with self.assertRaises(ValueError): self.client.start('duplicate')
        self.now = 21
        self.assertFalse(self.client.poll()['terminal'])
        self.assertEqual(len(self.calls),1)
        self.assertIsNone(self.client.poll())

    def test_correlated_rejection_and_rotated_journal(self):
        self.client.start('SHOW_INPUT_RECOVERY(0,10)')
        self.append(dict(self.record,event='message_rejected',reason='locked'),file='bridge_log')
        self.assertEqual(self.client.poll()['reason'],'locked')
        self.append(self.receipt())
        self.client.start('SHOW_INPUT_RECOVERY(0,10)')
        self.client.paths['command_log'].rename(self.root/'old.jsonl')
        self.append(self.receipt())
        self.assertTrue(self.client.poll()['terminal'])

    def test_full_page_of_maximum_unicode_text_is_readable(self):
        self.store.close()
        self.store = InputRecovery(self.root/'large.json')
        for index in range(10):
            self.store.admit('\u2603'*64000,dict(client_id='fixture',request_id=str(index),message_id=str(index)))
        self.client.start('SHOW_INPUT_RECOVERY(0,10)')
        self.append(self.receipt())
        page = recovery_page(self.client.poll())
        self.assertEqual(len(page['entries']),10)
        self.assertEqual(page['entries'][-1]['text'],'\u2603'*64000)


if __name__ == '__main__': unittest.main()
