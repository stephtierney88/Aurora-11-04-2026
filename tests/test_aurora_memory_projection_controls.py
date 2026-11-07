"""Opt-in projections, actual setters and contracts without native runtime import."""
import ast
from pathlib import Path
import threading
from types import SimpleNamespace as NS
import unittest
from aurora_settings_registry import coerce_setting_value, resolve_setting_definition, build_setting_readback
from aurora_command_contracts import validate_command_arguments

TREE = ast.parse((Path(__file__).resolve().parents[1] / 'aurora2.py').read_text(encoding='utf-8-sig'))
FUNCTIONS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}


class ProjectionControlsTests(unittest.TestCase):
    def setUp(self):
        self.s = dict(JOURNAL_ORDER='legacy', COMPLETED_GOAL_PROJECTION='legacy',
                      SETTINGS_TRANSACTION_LOCK=threading.RLock(),
                      coerce_setting_value=coerce_setting_value,
                      require_runtime_setting_unlocked=lambda *a: None,
                      display_message=lambda *a: None, agent_state=NS(tasks_list=[]))
        names = ['build_journal_projection', 'project_horizon_entries', 'build_completed_goal_projection', 'set_journal_order',
                 'set_journal_order_command', 'set_completed_goal_projection', 'set_completed_goal_projection_command']
        exec(compile(ast.Module(body=[FUNCTIONS[n] for n in names], type_ignores=[]), 'aurora2.py', 'exec'), self.s)

    def test_recent_tail_and_full_history(self):
        project = self.s['build_journal_projection']
        self.assertEqual(project(['a','b','c'], 2, 'recent').splitlines()[:2], ['- b', '- c'])
        self.assertIn('1 earlier', project(['a','b','c'], 2, 'recent'))
        self.assertEqual(project(['a','b'], None, 'recent'), '- a\n- b')
        self.assertNotIn('- a', project(['a'], 0, 'recent'))
        with self.assertRaises(ValueError): project(['a'], 1, 'invalid')

    def test_nested_completed_exact_match_hints_without_mutation(self):
        goal = NS(id=2, text='Deliver parcel', status='Complete', sub_goals=[])
        self.s['agent_state'].tasks_list = [NS(id=1, text='Journey', status='Incomplete', sub_goals=[goal])]
        items = ['Deliver parcel', 'Deliver parcel then heal', 'Another plan']
        self.assertEqual(self.s['project_horizon_entries'](items), items)
        self.s['set_completed_goal_projection']('annotate')
        result = self.s['project_horizon_entries'](items)
        self.assertIn('completed goal ID 2', result[0])
        self.assertEqual(result[1:], items[1:])
        self.assertEqual(items[0], 'Deliver parcel')
        goal.status = 'Incomplete'
        self.assertEqual(self.s['project_horizon_entries'](items), items)

    def test_active_duplicate_suppresses_hint(self):
        self.s['COMPLETED_GOAL_PROJECTION'] = 'annotate'
        self.s['agent_state'].tasks_list = [NS(id=i, text='Heal', status=status, sub_goals=[])
                                           for i,status in [(1,'Complete'),(2,'Incomplete')]]
        self.assertEqual(self.s['project_horizon_entries'](['Heal']), ['Heal'])

    def test_completion_history_opt_in_recent_and_non_mutating(self):
        entries = [{'timestamp': '2026-11-05 12:00:00', 'goal': 'Deliver parcel'},
                   {'timestamp': '2026-11-05 12:05:00', 'goal': 'Receive Pokedex'}]
        render = self.s['build_completed_goal_projection']
        self.assertEqual(render(entries), '')
        self.s['set_completed_goal_projection']('annotate')
        full = render(entries)
        self.assertIn('historical; not outcome verification', full)
        self.assertIn('[2026-11-05 12:00:00] Deliver parcel', full)
        recent = render(entries, 1)
        self.assertIn('Receive Pokedex', recent)
        self.assertNotIn('Deliver parcel', recent)
        self.assertIn('1 earlier retained records omitted', recent)
        self.assertEqual(entries[0], {'timestamp': '2026-11-05 12:00:00', 'goal': 'Deliver parcel'})
        self.s['set_completed_goal_projection']('legacy')
        self.assertEqual(render(entries), '')

    def test_completion_history_unknown_and_empty_records(self):
        self.s['COMPLETED_GOAL_PROJECTION'] = 'annotate'
        render = self.s['build_completed_goal_projection']
        self.assertEqual(render([]), '')
        self.assertIn('unknown time', render([{'goal': 'Old milestone'}]))
        self.assertIn('unknown goal', render([{}]))
        self.assertIn('Unreadable retained completion record', render(['legacy']))
        self.assertNotIn('Old milestone', render([{'goal': 'Old milestone'}], 0))

    def test_both_memory_views_use_shared_completion_projection(self):
        for name in ('build_agent_state_snapshot', 'update_pinned_information'):
            calls = [n for n in ast.walk(FUNCTIONS[name]) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == 'build_completed_goal_projection']
            self.assertEqual(len(calls), 1, name)

    def test_operator_settings_and_invalid_rollback(self):
        for name, key, variable, value in [('journal_order','memory.journal_order','JOURNAL_ORDER','recent'),
                                         ('completed_goal_projection','goals.completed_projection','COMPLETED_GOAL_PROJECTION','annotate')]:
            command = self.s[f'set_{name}_command']
            with self.assertRaises(ValueError): command([value], False)
            command([value], True)
            self.assertEqual(self.s[variable], value)
            with self.assertRaises(ValueError): command(['invalid'], True)
            self.assertEqual(self.s[variable], value)
            definition = resolve_setting_definition(key)
            state = {'modes': {definition.state_path[-1]: value}}
            self.assertEqual(build_setting_readback(key, state, runtime_active=True, state_age_seconds=0)['value'], value)
            validate_command_arguments(definition.command.split('(')[0], [value])
            command(['legacy'], True)
            self.assertEqual(self.s[variable], 'legacy')


if __name__ == '__main__': unittest.main()
