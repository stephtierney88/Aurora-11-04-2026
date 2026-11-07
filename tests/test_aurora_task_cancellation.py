"""Task identity, replacement and delayed input cleanup; no native/provider I/O."""
import ast
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from aurora_capture_provenance import CaptureService
from aurora_command_contracts import validate_command_arguments, describe_command_contract
from aurora_input_ownership import HeldInputLedger
from aurora_runtime_work import CancellationDomain
from aurora_task_continuation import TaskContinuation, TASK_CONTROL_RESULT_SCHEMA, parse_task_control_arguments


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'aurora2.py').read_text(encoding='utf-8-sig'))
FUNCTIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}


class ConditionalCancellationTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.task = TaskContinuation(clock=lambda: self.now)
        self.model, self.commands, self.inputs = CancellationDomain(), CancellationDomain(), HeldInputLedger()
        self.capture = CaptureService()
        self.displays = []
        self.scope = dict(TASK_CONTINUATION=self.task, TASK_CONTINUATION_MODE='bounded', MODEL_WORK=self.model,
            COMMAND_WORK=self.commands, HELD_INPUTS=self.inputs, CAPTURE_SERVICE=self.capture,
            SETTINGS_TRANSACTION_LOCK=threading.RLock(), TASK_CONTROL_RESULT_SCHEMA=TASK_CONTROL_RESULT_SCHEMA,
            parse_task_control_arguments=parse_task_control_arguments, json=json,
            cancel_capture_requests=self.capture.cancel, display_message=lambda *args: self.displays.append(args))
        exec(compile(ast.Module(body=[FUNCTIONS[name] for name in
            ('stop_model_turn_task', 'cancel_active_work_if_task_command')], type_ignores=[]), str(ROOT/'aurora2.py'), 'exec'), self.scope)
        self.task_id = self.reserve()

    def reserve(self):
        self.assertTrue(self.task.reserve(max_turns=10, max_seconds=30, operator_input=True))
        return self.task.snapshot()['task_id']

    def cancel(self, identity=None, is_user=True):
        return self.scope['cancel_active_work_if_task_command']([identity or self.task_id], is_user)

    def generations(self):
        return self.model.token().generation, self.commands.token().generation, self.capture.lifecycle

    def hold(self, key='a', release=None):
        return self.inputs.acquire(self.commands.token(),
            dict(namespace='fixture', kind='key', requested=key, effective=key, backend='fixture'),
            lambda: None, release or (lambda: None), persistent=True)

    def test_valid_and_invalid_contracts(self):
        self.assertEqual(parse_task_control_arguments('CANCEL_ACTIVE_WORK_IF_TASK', [f'"{self.task_id}"']), dict(task_id=self.task_id))
        validate_command_arguments('CANCEL_ACTIVE_WORK_IF_TASK', [self.task_id])
        for args in ([], ['all'], [self.task_id, 'extra'], ['task-'+'A'*32], ['task-'+'0'*31]):
            with self.assertRaises(ValueError):
                validate_command_arguments('CANCEL_ACTIVE_WORK_IF_TASK', args)
        self.assertEqual(describe_command_contract('CANCEL_ACTIVE_WORK_IF_TASK')['max_arguments'], 1)

    def test_invalid_id_never_calls_effects(self):
        before = self.generations()
        with self.assertRaises(ValueError):
            self.cancel('current')
        self.assertEqual(before, self.generations())

    def test_stale_id_preserves_replacement_and_all_generations(self):
        self.task.stop('done')
        replacement = self.reserve()
        lease = self.hold()
        before = self.generations()
        result = self.cancel()
        self.assertEqual(result['code'], 'stale_task')
        self.assertEqual(self.task.snapshot()['task_id'], replacement)
        self.assertEqual(self.task.snapshot()['status'], 'running')
        self.assertEqual(self.inputs.snapshot()['held'][0]['lease_id'], lease)
        self.assertEqual(before, self.generations())
        self.assertEqual(result['before'], result['after'])

    def test_stale_rejection_does_not_expire_another_task(self):
        self.now += 100
        result = self.cancel('task-'+'0'*32)
        self.assertEqual(result['after']['status'], 'running')
        self.assertEqual(self.task._task['status'], 'running')
        self.assertEqual(result['effects'], {})

    def test_actor_rejection_has_no_effects_even_with_current_id(self):
        before = self.generations()
        self.assertEqual(self.cancel(is_user=False)['code'], 'operator_only')
        self.assertEqual(before, self.generations())
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_legacy_mode_preserves_existing_work(self):
        self.scope['TASK_CONTINUATION_MODE'] = 'legacy'
        before = self.generations()
        self.assertEqual(self.cancel()['code'], 'bounded_required')
        self.assertEqual(before, self.generations())
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_matched_cancel_reports_scope_generations_and_cleanup(self):
        released = []
        self.hold(release=lambda: released.append('a'))
        before = self.generations()
        result = self.cancel()
        self.assertTrue(result['success'])
        self.assertEqual(result['schema_version'], TASK_CONTROL_RESULT_SCHEMA)
        self.assertEqual(result['after']['stop_reason'], 'operator_cancelled')
        self.assertEqual(self.generations(), tuple(value+1 for value in before))
        self.assertEqual(result['effects']['command_cancelled_through_generation'], before[1])
        self.assertEqual(released, ['a'])
        self.assertTrue(result['input_cleanup']['success'])
        self.assertFalse(result['remote_cancellation_confirmed'])
        self.assertIn('not task-isolated', result['scope'])

    def test_duplicate_does_not_cancel_new_unscoped_work_or_release_again(self):
        self.assertTrue(self.cancel()['success'])
        lease = self.hold()
        before = self.generations()
        result = self.cancel()
        self.assertEqual(result['code'], 'already_stopped')
        self.assertEqual(result['effect_status'], 'unchanged')
        self.assertEqual(before, self.generations())
        self.assertEqual(self.inputs.snapshot()['held'][0]['lease_id'], lease)
        self.assertNotIn('input_cleanup', result)

    def test_failed_release_remains_visible_and_duplicate_does_not_retry(self):
        attempts = []
        def fail_release():
            attempts.append('release')
            raise RuntimeError('fixture release failed')
        self.hold(release=fail_release)
        result = self.cancel()
        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'input_cleanup_uncertain')
        self.assertEqual(self.inputs.snapshot()['uncertain_count'], 1)
        self.cancel()
        self.assertEqual(attempts, ['release'])

    def test_partial_bookkeeping_failure_retains_captured_generation(self):
        self.hold()
        def fail_capture(reason):
            raise RuntimeError('PRIVATE fixture error')
        self.scope['cancel_capture_requests'] = fail_capture
        result = self.cancel()
        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'cancellation_uncertain')
        self.assertTrue(result['input_cleanup']['success'])
        self.assertIn('command_cancelled_through_generation', result['effects'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_delayed_cleanup_cannot_release_new_generation_hold(self):
        released = []
        self.hold(release=lambda: released.append('old'))
        original = self.inputs.cancel_through
        replacement = []
        def delayed(generation, reason):
            replacement.append(self.reserve())
            replacement.append(self.hold('b', release=lambda: released.append('new')))
            return original(generation, reason)
        self.inputs.cancel_through = delayed
        result = self.cancel()
        self.assertTrue(result['success'])
        self.assertNotEqual(self.task_id, replacement[0])
        self.assertEqual(released, ['old'])
        self.assertEqual(self.inputs.snapshot()['held'][0]['lease_id'], replacement[1])
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_concurrent_cancels_rotate_generations_once(self):
        before = self.generations()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.cancel(), range(2)))
        self.assertEqual(sorted(row['code'] for row in results), ['already_stopped', 'stopped'])
        self.assertEqual(self.generations(), tuple(value+1 for value in before))

    def test_replacement_cannot_cross_compare_and_cancel_boundary(self):
        entered, release, attempted, finished = (threading.Event() for _ in range(4))
        errors = []
        def callback(effects):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('fixture timeout')
        def cancel():
            try:
                self.task.stop_if_current(self.task_id, 'cancelled', on_stop=callback)
            except Exception as error:
                errors.append(error)
        def replace():
            attempted.set()
            try:
                self.reserve()
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()
        first, second = threading.Thread(target=cancel), threading.Thread(target=replace)
        first.start()
        try:
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(finished.wait(.05))
        finally:
            release.set()
            first.join(2)
            if second.ident is not None:
                second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertNotEqual(self.task_id, self.task.snapshot()['task_id'])
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_old_turn_finalization_cannot_stop_replacement(self):
        self.task.stop('finished')
        replacement = self.reserve()
        for reason in ('cancelled', 'turn_exception', 'model_turn_failed'):
            result = self.scope['stop_model_turn_task'](SimpleNamespace(task_id=self.task_id), reason)
            self.assertEqual(result['code'], 'stale_task')
        self.assertEqual(self.task.snapshot()['task_id'], replacement)
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_turn_without_reserved_task_cannot_stop_current_task(self):
        self.assertIsNone(self.scope['stop_model_turn_task'](SimpleNamespace(task_id=''), 'cancelled'))
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_current_turn_still_stops_its_own_task(self):
        result = self.scope['stop_model_turn_task'](SimpleNamespace(task_id=self.task_id), 'turn_exception')
        self.assertTrue(result['changed'])
        self.assertEqual(self.task.snapshot()['stop_reason'], 'turn_exception')
        self.assertEqual(result['effects'], {})


if __name__ == '__main__':
    unittest.main()
