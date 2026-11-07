import json
import unittest
from aurora_task_continuation import TaskContinuation
from aurora_task_objective import TaskObjectiveCapacity


class TaskObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.task = TaskContinuation(clock=lambda: self.now)

    def turn(self, **kwargs):
        return self.task.reserve(max_turns=20, max_seconds=100, **kwargs)

    def projection(self):
        return self.task.objective_projection(self.task.snapshot()['task_id'])

    def test_legacy_retains_no_text(self):
        self.turn(operator_input=True, operator_messages=['Original objective'])
        self.assertEqual(self.projection(), [])

    def test_original_and_clarification_survive_other_turns_verbatim(self):
        self.turn(objective_mode='operator', operator_input=True, operator_messages=['Visit town, then heal.'])
        self.turn(operator_input=True, operator_messages=['Correction: café first.\nKeep the budget.'])
        self.turn(operator_messages=['Synthetic screenshot or tool result'])
        message = self.projection()[0]
        self.assertEqual(message['role'], 'user')
        self.assertEqual(json.loads(message['content'].split('verbatim):\n')[1]),
                         ['Visit town, then heal.', 'Correction: café first.\nKeep the budget.'])
        self.assertEqual(self.task.snapshot()['objective']['messages'], 2)
        self.assertNotIn('Visit town', json.dumps(self.task.snapshot(include_progress=True)))
        message['content'] = 'mutated detached projection'
        self.assertIn('Visit town', self.projection()[0]['content'])

    def test_policy_is_latched_and_replacement_starts_fresh(self):
        self.turn(objective_mode='operator', operator_input=True, operator_messages=['Old task'])
        old = self.task.snapshot()['task_id']
        self.turn(objective_mode='legacy', operator_input=True, operator_messages=['Clarification'])
        self.assertEqual(self.task.snapshot()['objective']['messages'], 2)
        self.task.stop('cancelled')
        self.assertEqual(self.task.objective_projection(old), [])
        self.assertFalse(self.turn())
        self.turn(objective_mode='operator', operator_input=True, operator_messages=['Replacement'])
        self.assertNotEqual(old, self.task.snapshot()['task_id'])
        self.assertEqual(self.task.objective_projection(old), [])
        self.assertNotIn('Old task', self.projection()[0]['content'])
        self.task.stop('inference_paused')
        self.turn(operator_input=True, operator_messages=['Legacy replacement'])
        self.assertEqual(self.projection(), [])

    def test_deadline_erases_context_and_cannot_be_renewed_by_observation(self):
        self.turn(objective_mode='operator', operator_input=True, operator_messages=['Objective'])
        self.now = 101
        self.assertEqual(self.projection(), [])
        self.assertEqual(self.task.snapshot()['objective']['messages'], 0)
        self.assertFalse(self.turn(operator_messages=['Forged continuation']))

    def test_declared_done_clears_without_completing_goals(self):
        self.turn(objective_mode='operator', outcome_reporting=True, operator_input=True, operator_messages=['Objective'])
        result = self.task.report_outcome(self.task.snapshot()['task_id'], 'done', 'declared', actor='assistant')
        self.assertTrue(result['success'])
        self.assertEqual(self.projection(), [])

    def test_capacity_never_silently_drops_constraints(self):
        for messages in (['x'] * 33, ['x' * 32769], [None]):
            with self.subTest(messages_type=type(messages[0]).__name__):
                self.task = TaskContinuation(clock=lambda: self.now)
                self.turn(objective_mode='operator', operator_input=True, operator_messages=['Do not leave the target.'])
                with self.assertRaises(TaskObjectiveCapacity):
                    self.turn(operator_input=True, operator_messages=messages)
                self.assertEqual(self.task.snapshot()['stop_reason'], 'objective_capacity')
                self.assertEqual(self.projection(), [])

    def test_budget_not_reset_by_clarification(self):
        self.turn(objective_mode='operator', operator_input=True, operator_messages=['Original'])
        identity = self.task.snapshot()['task_id']
        self.now = 30
        self.turn(operator_input=True, operator_messages=['Clarify'])
        state = self.task.snapshot()
        self.assertEqual(state['task_id'], identity)
        self.assertEqual(state['remaining_seconds'], 70)
        self.assertEqual(state['turns'], 2)


if __name__ == '__main__':
    unittest.main()
