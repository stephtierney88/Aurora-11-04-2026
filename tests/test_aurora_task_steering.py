"""Exact-task operator context, literal text and version conflicts; no native I/O."""
import ast
import base64
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aurora_command_contracts import validate_command_arguments
from aurora_runtime_work import CancellationDomain, WorkCancelled
from aurora_task_continuation import TaskContinuation, TASK_CONTROL_RESULT_SCHEMA, parse_task_control_arguments
from aurora_task_objective import encode_steering_text, decode_steering_text


class TaskSteeringTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.task = TaskContinuation(clock=lambda: self.now)
        self.task.reserve(max_turns=8, max_seconds=60, objective_mode='operator', operator_input=True,
                          operator_messages=['ORIGINAL_PRIVATE: reach town, then heal.'])
        self.identity = self.task.snapshot()['task_id']

    def view(self):
        return self.task.inspect_context(self.identity)

    def version(self):
        return self.view()['context']['context_version']

    def test_literal_codec_preserves_quotes_unicode_whitespace_and_command_text(self):
        value = '  café 🌙\n"; CANCEL_ACTIVE_WORK();" \\ next\t'
        token = encode_steering_text(value)
        self.assertEqual(decode_steering_text(token), value)
        decoded = parse_task_control_arguments('STEER_TASK', [self.identity, self.version(), token])
        self.assertEqual(decoded['text'], value)
        validate_command_arguments('STEER_TASK', [self.identity, self.version(), token])

    def test_invalid_codec_inputs_reject_before_append(self):
        for text in ('', '   ', 'x'*32769, None, [], {'text': 'no'}, 123):
            with self.subTest(kind=type(text).__name__), self.assertRaises((ValueError, TypeError)):
                encode_steering_text(text)
        for token in ('!', 'a', 'A'*270001, base64.urlsafe_b64encode(b'"\\ud800"').decode(),
                      base64.urlsafe_b64encode(b'"\xff"').decode(), base64.urlsafe_b64encode(b'['*2000+b']'*2000).decode()):
            with self.subTest(token=token[:12]), self.assertRaises(ValueError):
                decode_steering_text(token)
        self.assertEqual(self.view()['context']['messages'], 1)

    def test_exact_argument_counts_and_version_format(self):
        for name, args in [('SHOW_TASK_CONTEXT', []), ('SHOW_TASK_CONTEXT', ['task-x']),
                           ('SHOW_TASK_CONTEXT', [self.identity, 'extra']), ('STEER_TASK', [self.identity]),
                           ('STEER_TASK', [self.identity, 'old', encode_steering_text('fix')])]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                validate_command_arguments(name, args)

    def test_inspection_is_detached_and_not_the_full_conversation(self):
        view = self.view()
        self.assertEqual(view['messages'][0]['source'], 'queued_operator_text')
        self.assertEqual(view['messages'][0]['role'], 'user')
        view['messages'][0]['text'] = 'changed copy'
        self.assertIn('ORIGINAL_PRIVATE', self.view()['messages'][0]['text'])
        self.assertNotIn('ORIGINAL_PRIVATE', json.dumps(self.task.snapshot(include_progress=True)))

    def test_stale_read_cannot_leak_or_expire_current_task(self):
        self.now = 100
        result = self.task.inspect_context('task-'+'0'*32)
        self.assertFalse(result['success'])
        self.assertNotIn('ORIGINAL_PRIVATE', json.dumps(result))
        self.assertNotIn('context', result)
        self.assertEqual(self.task._task['status'], 'running')

    def test_append_retains_original_role_source_and_order(self):
        result = self.task.steer(self.identity, self.version(), 'STEERING_PRIVATE: go to the café first.')
        self.assertTrue(result['changed'])
        view = self.view()
        self.assertEqual([row['source'] for row in view['messages']], ['queued_operator_text', 'operator_steering'])
        projected = self.task.objective_projection(self.identity)[0]
        self.assertEqual(projected['role'], 'user')
        self.assertIn('ORIGINAL_PRIVATE', projected['content'])
        self.assertIn('STEERING_PRIVATE', projected['content'])
        self.assertNotIn('STEERING_PRIVATE', json.dumps(result))
        self.assertNotIn('STEERING_PRIVATE', json.dumps(self.task.snapshot()))

    def test_append_changes_no_budgets_turns_or_wake(self):
        before = self.task.snapshot()
        self.now += 5
        result = self.task.steer(self.identity, self.version(), 'One clarification.')
        after = self.task.snapshot()
        self.assertFalse(result['wake_requested'])
        self.assertFalse(result['provider_delivery_confirmed'])
        for key in ('task_id', 'turns', 'max_turns', 'max_seconds', 'budgets', 'readback'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after['remaining_seconds'], 55)

    def test_duplicate_old_version_is_refused_without_second_append(self):
        version = self.version()
        first = self.task.steer(self.identity, version, 'Clarification.')
        second = self.task.steer(self.identity, version, 'Clarification.')
        self.assertTrue(first['success'])
        self.assertEqual(second['code'], 'context_conflict')
        self.assertEqual(self.view()['context']['messages'], 2)

    def test_same_version_concurrent_edits_have_one_winner(self):
        version = self.version()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda text: self.task.steer(self.identity, version, text), ['first', 'second']))
        self.assertEqual(sum(row['success'] for row in results), 1)
        self.assertEqual(self.view()['context']['messages'], 2)

    def test_ordinary_operator_input_invalidates_previously_read_version(self):
        version = self.version()
        self.task.reserve(max_turns=8, max_seconds=60, operator_input=True, operator_messages=['Ordinary clarification'])
        self.assertEqual(self.task.steer(self.identity, version, 'Stale edit')['code'], 'context_conflict')

    def test_capacity_refusal_preserves_current_context_and_running_task(self):
        for index in range(31):
            self.assertTrue(self.task.steer(self.identity, self.version(), f'brief {index}')['success'])
        before = self.view()
        result = self.task.steer(self.identity, self.version(), 'one too many')
        self.assertEqual(result['code'], 'context_capacity')
        self.assertEqual(before, self.view())
        self.assertEqual(self.task.snapshot()['status'], 'running')

    def test_character_capacity_refusal_is_atomic(self):
        before = self.view()
        result = self.task.steer(self.identity, self.version(), 'x'*32768)
        self.assertEqual(result['code'], 'context_capacity')
        self.assertEqual(before, self.view())

    def test_stopped_expired_and_replacement_tasks_are_not_restarted(self):
        version = self.version()
        self.now = 100
        self.assertEqual(self.task.steer(self.identity, version, 'late')['code'], 'task_stopped')
        self.assertEqual(self.task._task['status'], 'running')  # rejection is observational
        self.task.stop('cancelled')
        self.assertEqual(self.task.steer(self.identity, version, 'late')['code'], 'task_stopped')
        self.assertEqual(self.view()['messages'], [])
        self.task.reserve(max_turns=8, max_seconds=60, operator_input=True, objective_mode='operator', operator_messages=['Replacement private'])
        result = self.task.steer(self.identity, version, 'old-task edit')
        self.assertEqual(result['code'], 'stale_task')
        self.assertNotIn('Replacement private', json.dumps(result))

    def test_legacy_retention_cannot_be_enabled_by_steering(self):
        self.task.stop('done')
        self.task.reserve(max_turns=8, max_seconds=60, operator_input=True, objective_mode='legacy')
        self.identity = self.task.snapshot()['task_id']
        self.assertEqual(self.task.steer(self.identity, self.version(), 'edit')['code'], 'retention_disabled')
        self.assertEqual(self.view()['messages'], [])

    def test_prepared_text_and_metadata_stay_frozen_across_steering(self):
        prepared = self.task.prepare_objective(self.identity)
        old_version = prepared['metadata']['context_version']
        self.task.steer(self.identity, old_version, 'Arrived after preparation.')
        self.assertNotIn('Arrived after', json.dumps(prepared))
        current = self.task.prepare_objective(self.identity)
        self.assertNotEqual(old_version, current['metadata']['context_version'])
        self.assertIn('Arrived after', json.dumps(current))


class RuntimeTaskSteeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root/'aurora2.py').read_text(encoding='utf-8-sig'))
        cls.code = compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in {'execute_task_context_command', 'show_task_context_command', 'steer_task_command'}], type_ignores=[]), str(root/'aurora2.py'), 'exec')

    def setUp(self):
        self.task = TaskContinuation()
        self.task.reserve(max_turns=5, max_seconds=60, objective_mode='operator', operator_input=True, operator_messages=['Original'])
        self.identity = self.task.snapshot()['task_id']
        self.version = self.task.inspect_context(self.identity)['context']['context_version']
        self.work = CancellationDomain()
        self.scope = dict(TASK_CONTINUATION=self.task, TASK_CONTINUATION_MODE='bounded', SETTINGS_TRANSACTION_LOCK=threading.RLock(),
            COMMAND_WORK=self.work, TASK_CONTROL_RESULT_SCHEMA=TASK_CONTROL_RESULT_SCHEMA, parse_task_control_arguments=parse_task_control_arguments,
            require_runtime_setting_unlocked=lambda *args: None, display_message=lambda *args: None, json=json)
        exec(self.code, self.scope)

    def call(self, name='STEER_TASK', is_user=True):
        args = [self.identity, self.version, encode_steering_text('New private text')] if name == 'STEER_TASK' else [self.identity]
        return self.scope['execute_task_context_command'](name, args, is_user)

    def test_operator_receipts_use_shared_schema(self):
        for name in ('SHOW_TASK_CONTEXT', 'STEER_TASK'):
            result = self.call(name)
            self.assertTrue(result['success'])
            self.assertEqual(result['schema_version'], TASK_CONTROL_RESULT_SCHEMA)
            self.assertEqual(result['command'], name)

    def test_model_cannot_inspect_or_inject_operator_context(self):
        for name in ('SHOW_TASK_CONTEXT', 'STEER_TASK'):
            result = self.call(name, False)
            self.assertEqual(result['code'], 'operator_only')
            self.assertNotIn('Original', json.dumps(result))
        self.assertEqual(self.task.inspect_context(self.identity)['context']['messages'], 1)

    def test_legacy_runtime_mode_rejects_without_side_effects(self):
        self.scope['TASK_CONTINUATION_MODE'] = 'legacy'
        self.assertEqual(self.call()['code'], 'bounded_required')
        self.assertEqual(self.task.inspect_context(self.identity)['context']['context_version'], self.version)

    def test_execution_lock_blocks_append_but_allows_inspection(self):
        def locked(*args):
            raise RuntimeError('locked')
        self.scope['require_runtime_setting_unlocked'] = locked
        self.assertEqual(self.call()['code'], 'execution_locked')
        self.assertTrue(self.call('SHOW_TASK_CONTEXT')['success'])

    def test_cancelled_generation_cannot_publish_steering(self):
        token = self.work.token()
        self.work.cancel('fixture')
        self.work.current = lambda: token
        with self.assertRaises(WorkCancelled):
            self.call()
        self.assertEqual(self.task.inspect_context(self.identity)['context']['context_version'], self.version)


if __name__ == '__main__':
    unittest.main()
