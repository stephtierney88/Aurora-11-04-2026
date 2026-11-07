import copy
import json
from pathlib import Path
import tempfile
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from aurora_input_recovery import InputRecovery, identity_key, parse_arguments


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'recovery.json'
        self.store = InputRecovery(self.path, max_rows=3)
        self.addCleanup(self.store.close)
        self.identity = dict(client_id='operator', message_id='msg', request_id='req')

    def row(self):
        return self.store.snapshot()['entries'][0]

    def restart(self):
        self.store.close()
        self.store = InputRecovery(self.path, max_rows=3)
        self.addCleanup(self.store.close)

    def test_restart_holds_queue_without_replaying_and_rotates_tokens(self):
        self.store.admit('hello', self.identity)
        old = self.row()
        self.restart()
        row = self.row()
        self.assertEqual(row['phase'], 'held')
        self.assertNotEqual(old['version'], row['version'])
        with self.assertRaises(ValueError):
            self.store.act(old['entry_id'], old['version'], retry=True)
        new = self.store.act(row['entry_id'], row['version'], retry=True)
        self.assertEqual(new['phase'], 'queued')
        self.assertNotEqual(new['identity'], self.identity)
        self.assertEqual(new['original_identity'], self.identity)

    def test_original_identity_dedup_and_conflicts_survive_restart_and_retry(self):
        self.store.admit('hello', self.identity)
        self.assertFalse(self.store.admit('hello', self.identity))
        with self.assertRaises(ValueError):
            self.store.admit('different', self.identity)
        self.restart()
        row = self.row()
        self.store.act(row['entry_id'], row['version'], retry=True)
        self.assertFalse(self.store.admit('hello', self.identity))

    def test_interrupted_submission_is_uncertain_and_requires_acknowledgement(self):
        self.store.admit('hello', self.identity)
        self.assertEqual(self.store.claim([self.identity]), {identity_key(self.identity)})
        self.store.delivery([self.identity], 'preparing', 'turn', 1, False)
        self.store.delivery([self.identity], 'submitted', 'turn', 2, True)
        self.restart()
        row = self.row()
        self.assertEqual(row['phase'], 'uncertain')
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            self.store.act(row['entry_id'], row['version'], retry=True)
        new = self.store.act(row['entry_id'], row['version'], retry=True, allow_uncertain=True)
        self.assertEqual(new['attempt'], 2)
        self.store.delivery([self.identity], 'responded', 'old', 3, True)
        self.assertEqual(self.row()['phase'], 'queued')

    def test_cancelled_queue_cannot_be_claimed_and_stale_cancel_rejected(self):
        self.store.admit('hello', self.identity)
        row = self.row()
        self.store.act(row['entry_id'], row['version'])
        self.assertFalse(self.store.claim([self.identity]))
        with self.assertRaises(ValueError):
            self.store.act(row['entry_id'], row['version'])
        self.restart()
        self.assertEqual(self.row()['phase'], 'cancelled')

    def test_unclaimed_recovery_cannot_enter_model_turn(self):
        self.store.admit('hello', self.identity)
        with self.assertRaisesRegex(ValueError, 'claimed'):
            self.store.delivery([self.identity], 'preparing', 'turn', 1, False)
        self.assertEqual(self.row()['phase'], 'queued')

    def test_responded_does_not_replay_and_active_work_cannot_cancel_via_queue(self):
        self.store.admit('hello', self.identity)
        self.store.claim([self.identity])
        row = self.row()
        with self.assertRaises(ValueError): self.store.act(row['entry_id'], row['version'])
        self.store.delivery([self.identity], 'responded', 'turn', 1, True)
        row = self.row()
        with self.assertRaises(ValueError): self.store.act(row['entry_id'], row['version'], retry=True)
        self.restart()
        self.assertEqual(self.row()['phase'], 'responded')

    def test_abandoned_claim_records_not_sent(self):
        self.store.admit('hello', self.identity)
        self.store.claim([self.identity])
        self.store.abandon_claims([self.identity])
        self.assertEqual(self.row()['phase'], 'not_sent')

    def test_failed_atomic_write_preserves_memory_disk_and_removes_temporary(self):
        self.store.admit('hello', self.identity)
        original, before = self.path.read_bytes(), self.store.snapshot()
        with patch('aurora_input_recovery.os.replace', side_effect=OSError('fixture full')):
            with self.assertRaises(OSError): self.store.claim([self.identity])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.store.snapshot(), before)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_second_owner_cannot_open_and_corrupt_data_is_preserved(self):
        self.store.admit('hello', self.identity)
        with self.assertRaises(OSError): InputRecovery(self.path)
        self.store.close()
        self.path.write_text('{"schema_version":"broken","rows":{}}')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): InputRecovery(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_bounds_do_not_evict_dedup_evidence(self):
        for index in range(3): self.store.admit('hello', dict(self.identity, request_id=str(index)))
        with self.assertRaises(ValueError): self.store.admit('new', self.identity)
        self.assertEqual(self.store.snapshot(1,1)['total'], 3)
        with self.assertRaises(ValueError): parse_arguments('SHOW_INPUT_RECOVERY', ['0','101'])
        with self.assertRaises(ValueError): parse_arguments('RETRY_INPUT', ['a'*64,'b'*64,'yes'])

    def test_abrupt_process_exit_releases_lease_and_leaves_uncertain_input(self):
        self.store.admit('hello', self.identity)
        self.store.close()
        code = """import os,sys
from aurora_input_recovery import InputRecovery
s=InputRecovery(sys.argv[1]); r=s.snapshot()['entries'][0]
new=s.act(r['entry_id'],r['version'],retry=True)
s.claim([new['identity']]); s.delivery([new['identity']],'submitted','crash-turn',1,True)
os._exit(0)
"""
        process = subprocess.run([sys.executable, '-c', code, str(self.path)], timeout=10,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
        self.restart()
        self.assertEqual(self.row()['phase'], 'uncertain')
        self.assertTrue(self.row()['request_started'])

    def terminal(self, index=0, phase='responded', started=True):
        identity = dict(self.identity, request_id=f'terminal-{index}')
        self.store.admit(f'private fixture text {index}', identity)
        if phase == 'cancelled' and not started:
            row = self.store.snapshot()['entries'][-1]
            self.store.act(row['entry_id'],row['version'])
        else:
            self.store.claim([identity])
            self.store.delivery([identity],phase,f'turn-{index}',1,started)
        return identity

    def test_compaction_is_opt_in_v1_preserved_then_v2_deduplicates_after_restart(self):
        identity = self.terminal()
        before = self.path.read_bytes()
        preview = self.store.compaction_preview(0,1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(json.loads(before)['schema_version'],'aurora_input_recovery_v1')
        result = self.store.compact(0,1,preview['version'])
        self.assertEqual(result['compacted_count'],1)
        self.assertNotIn('private fixture text',self.path.read_text())
        self.assertEqual(self.store.summary()['schema_version'],'aurora_input_recovery_v2')
        self.restart()
        self.assertFalse(self.store.admit('private fixture text 0',identity))
        with self.assertRaisesRegex(ValueError,'different text'): self.store.admit('changed',identity)
        self.assertEqual(self.store.snapshot()['compacted'],1)
        self.assertEqual(self.store.snapshot()['entries'],[])

    def test_compaction_retains_newest_eligible_by_admission_and_keeps_uncertain(self):
        older = self.terminal(0)
        self.terminal(1,phase='cancelled',started=False)
        self.terminal(2,phase='cancelled',started=True)
        preview = self.store.compaction_preview(1,100)
        self.assertEqual([r['entry_id'] for r in preview['selected']],[identity_key(older)])
        self.store.compact(1,100,preview['version'])
        self.assertEqual([r['phase'] for r in self.store.snapshot()['entries']],['cancelled','cancelled'])
        self.assertEqual(self.store.compaction_preview(0,100)['selected_count'],1)

    def test_compaction_version_rejects_other_mutation_and_restart(self):
        self.terminal()
        preview=self.store.compaction_preview(0,10)
        self.store.admit('new pending',self.identity)
        with self.assertRaisesRegex(ValueError,'changed/reloaded'): self.store.compact(0,10,preview['version'])
        preview=self.store.compaction_preview(0,10)
        self.restart()
        with self.assertRaisesRegex(ValueError,'changed/reloaded'): self.store.compact(0,10,preview['version'])

    def test_compaction_disk_failure_keeps_text_and_hashes_atomic(self):
        self.terminal()
        preview=self.store.compaction_preview(0,10)
        before=self.path.read_bytes()
        with patch('aurora_input_recovery.os.replace',side_effect=OSError('fixture full')):
            with self.assertRaises(OSError): self.store.compact(0,10,preview['version'])
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.store.summary()['compacted'],0)
        self.assertEqual(self.store.summary()['total'],1)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_tombstone_capacity_preserves_evidence_and_bounds_each_batch(self):
        self.store.max_tombstones=1
        identity=self.terminal(0)
        self.terminal(1)
        self.store.admit('pending must stay',self.identity)
        preview=self.store.compaction_preview(0,100)
        self.assertEqual(preview['selected_count'],1)
        self.assertTrue(preview['capacity_blocked'])
        self.store.compact(0,100,preview['version'])
        self.assertFalse(self.store.admit('private fixture text 0',identity))
        again=self.store.compaction_preview(0,100)
        self.assertEqual(again['selected_count'],0)
        self.assertEqual(self.store.compact(0,100,again['version'])['compacted_count'],0)
        self.assertEqual(self.store.summary()['total'],2)

    def test_compaction_arguments_and_malformed_v2_fail_closed(self):
        self.assertEqual(parse_arguments('PREVIEW_INPUT_RECOVERY_COMPACTION',[]),dict(keep_terminal=20,limit=100))
        for args in (['0','101'],['-1','10']):
            with self.assertRaises(ValueError): parse_arguments('PREVIEW_INPUT_RECOVERY_COMPACTION',args)
        with self.assertRaises(ValueError): parse_arguments('COMPACT_INPUT_RECOVERY',['0','10','a'*64,'yes'])
        self.terminal()
        preview=self.store.compaction_preview(0,10)
        self.store.compact(0,10,preview['version'])
        self.store.close()
        data=json.loads(self.path.read_text())
        next(iter(data['tombstones'].values()))['text_sha256']='invalid'
        self.path.write_text(json.dumps(data))
        before=self.path.read_bytes()
        with self.assertRaises(ValueError): InputRecovery(self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_compaction_and_stale_writer_never_remove_new_input(self):
        from concurrent.futures import ThreadPoolExecutor
        self.terminal()
        preview=self.store.compaction_preview(0,10)
        def apply():
            try: return self.store.compact(0,10,preview['version'])['compacted_count']
            except ValueError: return 'stale'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:apply(),range(2)))
        self.assertCountEqual(results,[1,'stale'])
        self.store.admit('new pending',self.identity)
        self.assertEqual(self.store.snapshot()['entries'][0]['text'],'new pending')

    def test_failed_not_sent_and_waiting_payloads_are_not_compacted(self):
        self.terminal(0,phase='failed',started=False)
        self.terminal(1,phase='not_sent',started=False)
        self.store.admit('pending',self.identity)
        self.assertEqual(self.store.compaction_preview(0,100)['selected_count'],0)


if __name__ == '__main__': unittest.main()
