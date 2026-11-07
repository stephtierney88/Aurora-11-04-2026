import unittest
from aurora_capture_provenance import plan_batch_observation, dynamic_observation_guidance


class BatchCaptureTests(unittest.TestCase):
    def row(self, **changes):
        row = dict(command_batch_id='b1', command_generation=4,
                   capture_batch=dict(policy='batch_end', session_id='s1', lifecycle=2, requests=2, settle_seconds=.4))
        row.update(changes)
        return row

    def plan(self, rows):
        return plan_batch_observation(rows, session_id='s1', lifecycle=2, command_generation=4, default_settle=.2)

    def capture_only(self, delay=0, policy='batch_end_explicit'):
        row = self.row(success=True, executed_commands=['REQUEST_SCREENSHOT_CAPTURE(now,0)', 'request_demand_capture(again,0)'],
                       desktop_results=[], failed_commands=[], blocked_commands=[], cancelled_commands=[])
        row['capture_batch'].update(policy=policy, settle_seconds=delay)
        return row

    def test_explicit_capture_only_uses_requested_delay_without_default_floor(self):
        for delay in (0, .05, .4):
            info = self.plan([self.capture_only(delay)])[1]
            self.assertEqual(info['settle_seconds'], delay)
            self.assertEqual((info['explicit_only_batches'], info['default_settle_batches']), (1, 0))

    def test_original_batch_end_retains_default_for_capture_only(self):
        self.assertEqual(self.plan([self.capture_only(policy='batch_end')])[1]['settle_seconds'], .2)

    def test_mixed_or_input_receipts_retain_default_floor(self):
        for command in ('PYAG:press(a)', 'GB:up', 'UPDATE_CONTEXT(done)', 'UNKNOWN()'):
            row = self.capture_only()
            row['executed_commands'].append(command)
            self.assertEqual(self.plan([row])[1]['settle_seconds'], .2)
        row = self.capture_only()
        row['desktop_results'] = [dict(effect_status='uncertain')]
        self.assertEqual(self.plan([row])[1]['settle_seconds'], .2)

    def test_incomplete_failed_or_inconsistent_evidence_cannot_shorten_delay(self):
        for field in ('success', 'executed_commands', 'desktop_results', 'failed_commands', 'blocked_commands', 'cancelled_commands'):
            row = self.capture_only()
            del row[field]
            self.assertEqual(self.plan([row])[1]['settle_seconds'], .2, field)
        for field, value in [('success',False), ('failed_commands',['bad']), ('blocked_commands',['tail']),
                             ('cancelled_commands',['tail']), ('desktop_results',None), ('executed_commands',[])]:
            row = self.capture_only(); row[field] = value
            self.assertEqual(self.plan([row])[1]['settle_seconds'], .2, field)
        row = self.capture_only(); row['capture_batch']['requests'] = 1
        self.assertEqual(self.plan([row])[1]['settle_seconds'], .2)

    def test_mixed_receipt_drain_preserves_every_required_floor(self):
        for other in (self.row(), self.capture_only(policy='batch_end'), dict(command_batch_id='legacy')):
            rows, info = self.plan([self.capture_only(.01), other])
            self.assertEqual(len(rows), 2)
            self.assertGreaterEqual(info['settle_seconds'], .2)
            self.assertEqual(info['explicit_only_batches'], 1)

    def test_explicit_policy_still_rejects_old_generation_and_cancellation(self):
        for field, value in [('cancelled', True), ('command_generation',3)]:
            row = self.capture_only(); row[field] = value
            self.assertEqual(self.plan([row])[0], [])
        row = self.capture_only(); row['capture_batch']['lifecycle'] = 1
        self.assertEqual(self.plan([row])[0], [])

    def test_prompt_guidance_distinguishes_policies_and_observation_boundaries(self):
        self.assertIn('can produce an extra capture', dynamic_observation_guidance('legacy'))
        for policy in ('batch_end', 'batch_end_explicit'):
            text = dynamic_observation_guidance(policy)
            self.assertIn('policy='+policy, text)
            self.assertIn('not a visual feedback barrier', text)
            self.assertIn('does not verify visual stability', text)
            self.assertNotIn('can produce an extra capture', text)
        self.assertIn('including to capture-only batches', dynamic_observation_guidance('batch_end'))
        self.assertIn('zero if omitted', dynamic_observation_guidance('batch_end_explicit'))

    def test_single_receipt_coalesces_and_preserves_longest_settle(self):
        rows, info = self.plan([self.row()])
        self.assertEqual((len(rows), info['deferred_requests'], info['settle_seconds']), (1, 2, .4))

    def test_multiple_terminal_batches_share_later_boundary(self):
        a, b = self.row(), self.row(command_batch_id='b2')
        b['capture_batch']['settle_seconds'] = .6
        self.assertEqual(self.plan([a, b])[1]['settle_seconds'], .6)
        self.assertEqual(self.plan([a, b])[1]['deferred_requests'], 4)

    def test_cancelled_generation_and_lifecycle_are_rejected(self):
        for changes in ({'cancelled': True}, {'command_generation': 3}):
            self.assertEqual(self.plan([self.row(**changes)])[0], [])
        for key, value in [('session_id','other'), ('lifecycle',1)]:
            row = self.row(); row['capture_batch'][key] = value
            self.assertEqual(self.plan([row])[0], [])

    def test_legacy_receipt_is_unchanged(self):
        row = dict(command_batch_id='legacy', cancelled=True)
        selected, info = self.plan([row])
        self.assertEqual(selected, [row])
        self.assertEqual(info['settle_seconds'], .2)

    def test_failed_partial_batch_can_be_observed_without_replay(self):
        self.assertEqual(len(self.plan([self.row(success=False)])[0]), 1)

    def test_invalid_delay_is_not_converted_to_immediate_capture(self):
        for value in [-1, float('nan'), float('inf'), 'bad']:
            row = self.row(); row['capture_batch']['settle_seconds'] = value
            self.assertEqual(self.plan([row])[0], [])


if __name__ == '__main__':
    unittest.main()
