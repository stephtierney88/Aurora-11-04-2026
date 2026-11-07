"""Exact receipt reconciliation without resending input or restoring context."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from aurora_delivery_receipts import TurnDelivery
from aurora_input_recovery import InputRecovery, parse_arguments, describe_contract
from aurora_recovery_reconciliation import delivery_evidence
from aurora_command_contracts import validate_command_arguments, reviewed_command_description


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aurora-reconciliation-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'recovery.json';self.log=Path(self.temp.name)/'receipts.jsonl'
        self.store=InputRecovery(self.path);self.addCleanup(self.store.close)
        self.identity=dict(client_id='fixture',request_id='request',message_id='message')
        self.store.admit('PRIVATE_FIXTURE_TEXT',self.identity);self.store.claim([self.identity])
        self.delivery=TurnDelivery(self.write,[self.identity],guard=self.guard)
        for phase in ('preparing','prepared','submitted'):self.delivery.emit(phase)
        self.delivery.guard=None;self.delivery.emit('responded')  # Durable terminal write was lost.

    def write(self,event,**fields):
        with self.log.open('a',encoding='utf-8') as handle:handle.write(json.dumps(dict(event=event,**fields))+'\n')
    def guard(self,delivery,phase):
        self.store.delivery(delivery.references,phase,delivery.inference_request_id,delivery.sequence+1,
                            delivery.request_started or phase=='submitted')
    def row(self):return self.store.snapshot()['entries'][0]
    def preview(self):
        row=self.row();return self.store.preview_reconciliation(row['entry_id'],row['version'],self.log)
    def apply(self,preview=None,**kwargs):
        p=preview or self.preview()
        return self.store.reconcile_delivery(p['entry_id'],p['version'],p['evidence_version'],self.log,**kwargs)
    def events(self):return [json.loads(line) for line in self.log.read_text().splitlines()]
    def replace_events(self,events):self.log.write_text(''.join(json.dumps(row)+'\n' for row in events),encoding='utf-8')

    def test_preview_is_nonmutating_and_bounded_metadata_only(self):
        before=self.path.read_bytes();result=self.preview()
        self.assertEqual(before,self.path.read_bytes());self.assertEqual(result['before']['phase'],'submitted')
        self.assertEqual(result['after']['phase'],'responded');self.assertEqual(result['evidence']['receipt_count'],4)
        self.assertNotIn('PRIVATE_FIXTURE_TEXT',json.dumps(result));self.assertNotIn(str(self.log),json.dumps(result))
        self.assertTrue(result['apply_command'].startswith('RECONCILE_INPUT_DELIVERY('))

    def test_apply_updates_only_bookkeeping_survives_restart_no_replay(self):
        old=self.row();self.apply();new=self.row()
        for key in ('identity','original_identity','text','attempt','turn_id'):self.assertEqual(new[key],old[key])
        self.assertEqual(new['phase'],'responded');self.assertEqual(new['revision'],old['revision']+1)
        self.store.close();self.store=InputRecovery(self.path);self.addCleanup(self.store.close)
        self.assertEqual(self.row()['phase'],'responded');self.assertFalse(self.store.admit(old['text'],self.identity))
        with self.assertRaises(ValueError):self.store.act(self.row()['entry_id'],self.row()['version'],retry=True)

    def test_restart_uncertainty_reconciles_but_old_version_fails(self):
        old=self.preview();self.store.close();self.store=InputRecovery(self.path);self.addCleanup(self.store.close)
        self.assertEqual(self.row()['phase'],'uncertain')
        with self.assertRaisesRegex(ValueError,'changed/reloaded'):self.apply(old)
        self.apply();self.assertEqual(self.row()['phase'],'responded')

    def test_changed_row_rejects_stale_preview(self):
        preview=self.preview();self.store.delivery([self.identity],'failed',self.row()['turn_id'],4,True)
        with self.assertRaisesRegex(ValueError,'changed/reloaded'):self.apply(preview)
        self.assertEqual(self.row()['phase'],'failed')

    def test_changed_matching_receipt_rejects_stale_preview(self):
        preview=self.preview();events=self.events();events[-1]['reason']='changed';self.replace_events(events)
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.apply(preview)
        self.assertEqual(self.row()['phase'],'submitted')

    def test_unrelated_append_does_not_invalidate_preview(self):
        preview=self.preview();self.write('command_result',status='fixture unrelated')
        self.apply(preview);self.assertEqual(self.row()['phase'],'responded')

    def test_rotation_requires_new_preview_even_identical_contents(self):
        preview=self.preview();replacement=self.log.with_suffix('.next');replacement.write_bytes(self.log.read_bytes());replacement.replace(self.log)
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.apply(preview)
        self.apply();self.assertEqual(self.row()['phase'],'responded')

    def test_partial_tail_unknown_until_newline(self):
        raw=self.log.read_bytes();self.log.write_bytes(raw[:-1])
        with self.assertRaisesRegex(ValueError,'incomplete'):self.preview()
        self.log.write_bytes(raw);self.apply()

    def test_missing_start_or_gap_or_out_of_order_refuses(self):
        events=self.events()
        for broken in (events[1:],events[:1]+events[2:],[events[0],events[2],events[1],events[3]]):
            self.replace_events(broken)
            with self.assertRaises(ValueError):self.preview()
        self.assertEqual(self.row()['phase'],'submitted')

    def test_exact_duplicate_allowed_conflicting_terminal_refused(self):
        events=self.events();self.replace_events(events+[events[-1]])
        self.assertEqual(self.preview()['after']['phase'],'responded')
        conflict=dict(events[-1],phase='cancelled');self.replace_events(events+[conflict])
        with self.assertRaisesRegex(ValueError,'Conflicting'):self.preview()

    def test_unrelated_identity_and_turn_do_not_supply_missing_terminal(self):
        events=self.events()
        for field in ('request_id','client_id','message_id','inference_request_id'):
            bad=copy.deepcopy(events);bad[-1][field]='other';self.replace_events(bad)
            with self.assertRaisesRegex(ValueError,'No complete terminal'):self.preview()

    def test_unsupported_schema_types_and_started_flag_refused(self):
        events=self.events()
        for field,value in [('delivery_schema',True),('delivery_schema',2),('sequence',True),('request_started',False),('phase','unknown')]:
            bad=copy.deepcopy(events);bad[-1][field]=value;self.replace_events(bad)
            with self.assertRaises(ValueError):self.preview()

    def test_regressed_durable_start_evidence_refused(self):
        row=self.row();row['request_started']=False
        with self.assertRaisesRegex(ValueError,'durable delivery frontier'):delivery_evidence(self.log,row)

    def test_malformed_and_duplicate_json_fields_refuse(self):
        original=self.log.read_bytes()
        for raw in (b'{broken}\n',b'{"event":"a","event":"b"}\n',b'[]\n'):
            self.log.write_bytes(original+raw)
            with self.assertRaises(ValueError):self.preview()

    def test_large_window_is_bounded_and_reports_prefix_omission(self):
        chain=self.log.read_bytes();self.log.write_bytes(b'{"padding":"'+b'x'*20000+b'"}\n'+chain)
        with patch('aurora_recovery_reconciliation.MAX_SCAN_BYTES',len(chain)+200):
            preview=self.preview();self.assertTrue(preview['coverage']['prefix_omitted'])
            self.assertLessEqual(preview['coverage']['bytes_read'],len(chain)+200)
        with patch('aurora_recovery_reconciliation.MAX_SCAN_RECORDS',2):
            with self.assertRaises(ValueError):self.preview()

    def test_disk_failure_preserves_state_and_file(self):
        preview=self.preview();before=self.path.read_bytes();row=self.row()
        with patch('aurora_input_recovery.os.replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.apply(preview)
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(self.row(),row)

    def test_cancel_before_commit_preserves_state(self):
        before=self.path.read_bytes()
        def cancelled():raise RuntimeError('fixture cancelled')
        with self.assertRaises(RuntimeError):self.apply(before_publish=cancelled)
        self.assertEqual(self.path.read_bytes(),before)

    def test_early_not_sent_and_failed_are_reconciled_without_started_claim(self):
        for phase in ('not_sent','failed','cancelled'):
            path=Path(self.temp.name)/('recovery-'+phase+'.json');store=InputRecovery(path)
            try:
                identity=dict(self.identity,request_id=phase);store.admit('fixture',identity);store.claim([identity])
                log=Path(self.temp.name)/(phase+'.jsonl')
                def writer(event,**fields):
                    with log.open('a') as f:f.write(json.dumps(dict(event=event,**fields))+'\n')
                delivery=TurnDelivery(writer,[identity]);delivery.emit('preparing')
                store.delivery([identity],'preparing',delivery.inference_request_id,1,False)
                delivery.emit(phase)
                row=store.snapshot()['entries'][0];p=store.preview_reconciliation(row['entry_id'],row['version'],log)
                result=store.reconcile_delivery(p['entry_id'],p['version'],p['evidence_version'],log)
                self.assertEqual(result['after'],dict(phase=phase,sequence=2,request_started=False))
            finally:store.close()

    def test_contracts_validate_exact_hashes_and_discovery_signature(self):
        for name,count in [('PREVIEW_INPUT_RECONCILIATION',2),('RECONCILE_INPUT_DELIVERY',3)]:
            validate_command_arguments(name,['a'*64]*count)
            with self.assertRaises(ValueError):parse_arguments(name,['a'*64]*(count-1))
            with self.assertRaises(ValueError):parse_arguments(name,['bad']*count)
            self.assertEqual(describe_contract(name)['max_arguments'],count)
        self.assertIn('evidence_version',reviewed_command_description('RECONCILE_INPUT_DELIVERY')['signature'])


if __name__=='__main__':unittest.main()
