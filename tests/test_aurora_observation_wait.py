import unittest
from dataclasses import replace

from aurora_capture_geometry import CaptureTarget, FrameGeometry
from aurora_capture_provenance import CaptureService
from aurora_observation_wait import (observe_screen_change, parse_observation_arguments,
                                     describe_observation_contract, baseline_frame)
from aurora_runtime_work import WorkCancelled
from aurora_command_contracts import validate_command_arguments, command_failure_stops_batch
from aurora_task_continuation import CommandReadbacks


class ObservationWaitTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.service = CaptureService(epoch=lambda: 1000+self.now, monotonic=lambda: self.now)
        self.geometry = FrameGeometry((20,20),(20,20),
            CaptureTarget('foreground',(0,0,20,20),(0,0,100,100),(0,0,20,20),1,2,96),
            'per_monitor_v2','verified')
        self.publish('initial')
        self.baseline = self.service.latest['provenance']['frame_id']
        self.events = []
        self.sample_hashes = ['initial','changed']
        self.sample_hook = None
        self.block = False
        self.cancel = False

    def publish(self, hash_value, geometry=None):
        stamp = self.service.finish(self.service.begin('fixture'))
        self.service.publish(stamp,path='fixture.png',timestamp='fixture',capture_hash=hash_value,
                             counter=self.service.sequence,geometry=geometry or self.geometry)

    def request(self, remaining, first):
        generation = self.service.request('observation',timeout_seconds=remaining,max_attempts=1)
        self.events.append((generation, first))
        return generation

    def wait(self, duration):
        self.now += duration
        if self.sample_hook:
            hook,self.sample_hook=self.sample_hook,None
            hook()
        if self.service.pending and not self.block:
            value = self.sample_hashes.pop(0) if self.sample_hashes else 'initial'
            self.publish(value)

    def check(self):
        if self.cancel:
            raise WorkCancelled('fixture cancel')

    def run_wait(self, timeout=.5, interval=.1):
        return observe_screen_change(self.service,self.baseline,timeout,interval,
            request=self.request,check=self.check,wait=self.wait,monotonic=lambda:self.now)

    def test_changed_after_unchanged_sample(self):
        result=self.run_wait()
        self.assertEqual((result['status'],result['samples'],result['condition_met']),('changed',2,True))
        self.assertEqual(result['frame_id'],self.service.latest['provenance']['frame_id'])
        self.assertNotEqual(result['frame_id'],self.baseline)
        self.assertTrue(result['success'])
        self.assertFalse(self.service.pending)

    def test_unchanged_timeout_is_completed_observation_not_game_failure(self):
        self.sample_hashes=[]
        result=self.run_wait()
        self.assertEqual(result['status'],'timeout')
        self.assertFalse(result['condition_met'])
        self.assertTrue(result['success'])
        self.assertLessEqual(result['elapsed_seconds'],.5)
        self.assertFalse(self.service.pending)

    def test_sample_limit_bounds_requests(self):
        self.sample_hashes=[]
        result=self.run_wait(8,.1)
        self.assertEqual((result['status'],result['requested_samples']),('sample_limit',12))

    def test_stale_baseline_no_side_effect(self):
        self.publish('newer')
        result=self.run_wait()
        self.assertEqual(result['status'],'not_started')
        self.assertFalse(self.events)

    def test_pending_and_inflight_refused(self):
        self.service.request('other')
        with self.assertRaises(ValueError): baseline_frame(self.service,self.baseline)
        self.service.cancel('fixture')
        self.publish('initial')
        self.baseline=self.service.latest['provenance']['frame_id']
        self.service.begin('inflight')
        with self.assertRaises(ValueError): baseline_frame(self.service,self.baseline)

    def test_unknown_geometry_or_missing_fingerprint_refused(self):
        self.service.latest['geometry']['status']='unknown'
        self.assertEqual(self.run_wait()['status'],'not_started')
        self.assertFalse(self.events)

    def test_geometry_change_never_claims_progress(self):
        moved=replace(self.geometry,target=CaptureTarget('foreground',(1,0,21,20),(0,0,100,100),(1,0,21,20),1,2,96))
        self.sample_hook=lambda: self.publish('changed',moved)
        self.block=True
        result=self.run_wait()
        self.assertEqual(result['status'],'incomparable')
        self.assertIsNone(result['condition_met'])

    def test_newer_request_not_consumed_or_cancelled(self):
        self.block=True
        self.sample_hook=lambda: self.service.request('newer',2)
        result=self.run_wait()
        self.assertEqual(result['status'],'superseded')
        self.assertEqual(self.service.pending['reason'],'newer')

    def test_cancel_releases_only_own_request_and_fences_late_frame(self):
        stamps=[]
        def cancel():
            stamps.append(self.service.begin('slow'))
            self.cancel=True
        self.sample_hook=cancel
        self.block=True
        result=self.run_wait()
        self.assertEqual(result['status'],'cancelled')
        self.assertFalse(self.service.pending)
        self.assertFalse(self.service.accepts(self.service.finish(stamps[0])))

    def test_lifecycle_cancel_cannot_restart_capture(self):
        self.sample_hook=lambda:self.service.cancel('runtime replaced')
        self.block=True
        result=self.run_wait()
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(len(self.events),1)

    def test_no_publication_is_failure_and_fenced(self):
        self.block=True
        result=self.run_wait()
        self.assertEqual(result['status'],'capture_failed')
        self.assertIsNone(result['condition_met'])
        self.assertFalse(self.service.pending)
        self.assertTrue(self.service.snapshot()['current_failure'])

    def test_older_completion_does_not_satisfy_new_sample(self):
        old=self.service.finish(self.service.begin('pre-request'))
        self.sample_hook=lambda:self.service.publish(old,path='old.png',timestamp='old',capture_hash='different',counter=2,geometry=self.geometry)
        self.block=True
        result=self.run_wait()
        self.assertEqual(result['status'],'capture_failed')
        self.assertEqual(result['samples'],0)

    def test_parameters_and_contract(self):
        self.assertEqual(parse_observation_arguments([self.baseline]),(self.baseline,3,.25))
        for args in ([],['latest'],[self.baseline,'nan'],[self.baseline,9],[self.baseline,.1],
                     [self.baseline,1,0],[self.baseline,1,2],[self.baseline,1,.2,'extra']):
            with self.assertRaises(ValueError): validate_command_arguments('OBSERVE_SCREEN_CHANGE',args)
        self.assertTrue(command_failure_stops_batch('OBSERVE_SCREEN_CHANGE'))
        self.assertEqual(describe_observation_contract()['result']['receipt_field'],'observation_results')

    def test_receipt_can_continue_through_shared_readbacks(self):
        result=self.run_wait()
        store=CommandReadbacks()
        self.assertTrue(store.publish(dict(command_batch_id='b',task_id='t',inference_request_id='r',
                                           is_user=False,observation_results=[result])))
        records=store.prepare('t','next')['records']
        self.assertEqual(records[0]['results']['observation_results'][0]['status'],'changed')


if __name__=='__main__': unittest.main()
