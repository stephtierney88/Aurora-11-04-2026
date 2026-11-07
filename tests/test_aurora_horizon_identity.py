import copy
import json
from pathlib import Path
import tempfile
import unittest

from aurora_horizon_identity import HorizonIdentityLedger, HORIZON_FIELDS, IDENTITY_COMMANDS, parse_identity_arguments
from aurora_goal_store import Goal, encode_goals, decode_goals, validate_document, write_document, read_document, IDENTITY_TASK_SCHEMA
from aurora_command_contracts import validate_command_arguments, describe_command_contract, command_failure_stops_batch


class HorizonIdentityTests(unittest.TestCase):
    def setUp(self):
        self.stores = {field: [] for field in HORIZON_FIELDS.values()}
        self.field = HORIZON_FIELDS['immediate']
        self.stores[self.field] = ['Reach town', 'Find map']
        self.ledger = HorizonIdentityLedger(self.stores)
        self.goal = Goal('Reach town', id=3)
        self.goals = encode_goals([self.goal], include_identity=True)

    def first(self, ledger=None):
        return (ledger or self.ledger).inspect(self.goals)['entries'][0]

    def link(self):
        row = self.first()
        return self.ledger.link(row['entry_id'], row['version'], self.goal.uid, self.goals)

    def state(self):
        return dict(self.stores, goals_list=self.goals, horizon_identity=self.ledger.export())

    def test_noop_preserves_identity_and_explicit_link_changes_version(self):
        before = self.first()
        self.ledger.sync(copy.deepcopy(self.stores))
        self.assertEqual(before, self.first())
        self.assertTrue(self.link()['changed'])
        after = self.first()
        self.assertEqual(before['entry_id'], after['entry_id'])
        self.assertNotEqual(before['version'], after['version'])
        self.assertEqual(after['goal']['id'], 3)
        self.assertFalse(self.ledger.link(after['entry_id'], after['version'], self.goal.uid, self.goals)['changed'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.ledger.link(before['entry_id'], before['version'], None, self.goals)

    def test_clear_and_reinsert_cannot_resurrect_identity_or_link(self):
        self.link()
        old = self.first()
        original = list(self.stores[self.field])
        self.stores[self.field] = []
        self.ledger.sync(self.stores)
        self.stores[self.field] = original
        self.ledger.sync(self.stores)
        self.assertNotEqual(old['entry_id'], self.first()['entry_id'])
        self.assertIsNone(self.first()['goal_uid'])
        with self.assertRaises(ValueError):
            self.ledger.link(old['entry_id'], old['version'], None, self.goals)

    def test_one_store_change_leaves_other_store_identity_alone(self):
        self.stores['mid_term_context'] = ['Reach town', 'Reach town']
        self.ledger.sync(self.stores)
        medium = self.ledger.inspect(self.goals, 'medium')['entries']
        self.assertNotEqual(medium[0]['entry_id'], medium[1]['entry_id'])
        self.stores[self.field].reverse()
        self.ledger.sync(self.stores)
        self.assertEqual(medium, self.ledger.inspect(self.goals, 'medium')['entries'])

    def test_numeric_id_or_text_reuse_does_not_rebind_missing_goal(self):
        self.link()
        replacement = encode_goals([Goal(self.goal.text, id=self.goal.id)], include_identity=True)
        row = self.ledger.inspect(replacement)['entries'][0]
        self.assertEqual(row['link_state'], 'missing')
        self.assertIn('linked goal missing', self.ledger.project(self.field, replacement)[0])
        before = self.ledger.export()
        with self.assertRaisesRegex(ValueError, 'no longer exists'):
            self.ledger.link(row['entry_id'], row['version'], self.goal.uid, replacement)
        self.assertEqual(before, self.ledger.export())

    def test_unlink_and_declared_status_projection_without_source_mutation(self):
        self.link()
        self.goals[0]['status'] = 'Complete'
        self.assertIn('Complete; declared status', self.ledger.project(self.field, self.goals)[0])
        row = self.first()
        self.ledger.link(row['entry_id'], row['version'], None, self.goals)
        self.assertIn('unlinked', self.ledger.project(self.field, self.goals)[0])
        self.assertEqual(self.stores[self.field], ['Reach town', 'Find map'])

    def test_pagination_and_goal_readback(self):
        page = self.ledger.inspect(self.goals, offset=1, limit=1)
        self.assertEqual((page['total'], page['omitted_before'], page['omitted_after']), (2, 1, 0))
        self.assertEqual(self.ledger.inspect(self.goals, 'goals')['entries'][0]['goal_uid'], self.goal.uid)
        self.assertEqual(self.ledger.inspect(self.goals, offset=999)['entries'], [])

    def test_versioned_save_restores_ids_but_rejects_preload_tokens(self):
        self.link()
        old = self.first()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            receipt = write_document(path, self.state())
            self.assertEqual(receipt['document_schema'], IDENTITY_TASK_SCHEMA)
            loaded, _, _ = read_document(path)
        self.assertEqual(decode_goals(loaded['goals_list'])[0].uid, self.goal.uid)
        ledger = HorizonIdentityLedger(loaded, loaded['horizon_identity'])
        self.assertEqual(old['entry_id'], self.first(ledger)['entry_id'])
        self.assertEqual(old['goal_uid'], self.first(ledger)['goal_uid'])
        self.assertNotEqual(old['version'], self.first(ledger)['version'])
        with self.assertRaises(ValueError):
            ledger.link(old['entry_id'], old['version'], None, self.goals)

    def test_legacy_save_preserves_old_shape_and_discloses_metadata_loss(self):
        self.link()
        state = self.state()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            receipt = write_document(path, state, format='legacy')
            loaded, _, _ = read_document(path)
        self.assertTrue(receipt['identity_omitted'])
        self.assertNotIn('horizon_identity', loaded)
        self.assertNotIn('uid', loaded['goals_list'][0])
        self.assertIn('horizon_identity', state)
        self.assertNotEqual(decode_goals(loaded['goals_list'])[0].uid, self.goal.uid)

    def test_corrupt_sidecar_rejected_before_file_replacement(self):
        mutations = [
            lambda state: state['horizon_identity']['rows'][self.field][0].update(text='wrong'),
            lambda state: state['horizon_identity']['rows'][self.field][1].update(entry_id=state['horizon_identity']['rows'][self.field][0]['entry_id']),
            lambda state: state['horizon_identity']['rows'][self.field][0].update(revision=True),
            lambda state: state['goals_list'][0].update(uid='bad'),
            lambda state: state['goals_list'].append(dict(state['goals_list'][0], id=99)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            write_document(path, self.state())
            original = path.read_bytes()
            for mutate in mutations:
                state = self.state()
                mutate(state)
                with self.assertRaises(ValueError):
                    write_document(path, state)
                self.assertEqual(original, path.read_bytes())

    def test_schema_boundaries_and_nested_goal_uids(self):
        self.goal.add_sub_goal(Goal('child'))
        rows = encode_goals([self.goal], include_identity=True)
        state = dict(self.state(), goals_list=rows)
        restored = decode_goals(validate_document(state)['goals_list'])
        self.assertEqual(restored[0].sub_goals[0].uid, self.goal.sub_goals[0].uid)
        with self.assertRaises(ValueError):
            validate_document({'schema_version': 'aurora_tasks_v1', 'state': state})
        with self.assertRaises(ValueError):
            validate_document({'schema_version': IDENTITY_TASK_SCHEMA, 'state': {'goals_list': []}})

    def test_command_contracts_strict_tokens_and_bounds(self):
        for command in IDENTITY_COMMANDS:
            self.assertTrue(command_failure_stops_batch(command))
            self.assertEqual(describe_command_contract(command)['result']['receipt_field'], 'memory_command_results')
        for args in (['all', '-1'], ['all', '0', '201'], ['future'], ['all', '0.2'], ['all', '0', '1', 'lost']):
            with self.assertRaises(ValueError):
                validate_command_arguments('SHOW_HORIZON_ENTRIES', args)
        row = self.first()
        args = [row['entry_id'], row['version'], self.goal.uid]
        validate_command_arguments('LINK_HORIZON_GOAL', args)
        self.assertEqual(parse_identity_arguments('LINK_HORIZON_GOAL', args)['goal_uid'], self.goal.uid)
        for invalid in (args[:2], args[:2]+['3'], ['bad']+args[1:]):
            with self.assertRaises(ValueError):
                validate_command_arguments('LINK_HORIZON_GOAL', invalid)


if __name__ == '__main__':
    unittest.main()
