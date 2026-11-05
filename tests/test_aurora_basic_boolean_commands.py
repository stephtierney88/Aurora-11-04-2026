"""Basic toggle admission/query/failure guarantees without GUI or runtime import."""
import ast
import unittest

import test_aurora_command_ingress as ingress
from aurora_command_contracts import (
    SIMPLE_BOOLEAN_COMMANDS, REGISTERED_SETTING_COMMANDS, parse_boolean_command_arguments,
    validate_command_arguments, describe_command_contract, command_failure_stops_batch,
)


class BooleanCommandTests(unittest.TestCase):
    def test_queries_aliases_and_no_duplicate_setting_authority(self):
        self.assertFalse(SIMPLE_BOOLEAN_COMMANDS.intersection(REGISTERED_SETTING_COMMANDS))
        for name in SIMPLE_BOOLEAN_COMMANDS:
            self.assertIsNone(parse_boolean_command_arguments(name, []))
            self.assertTrue(command_failure_stops_batch(name))
            self.assertEqual(describe_command_contract(name)['max_arguments'], 1)
            for value, expected in [('ON', True), ('yes', True), ('1', True), ('true', True),
                                    (' off ', False), ('no', False), ('0', False), ('false', False)]:
                self.assertIs(parse_boolean_command_arguments(name, [value]), expected)
            for args in ([''], ['typo'], ['on', 'ignored'], [None]):
                with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                    validate_command_arguments(name, args)

    def test_direct_runtime_parser_distinguishes_query_from_bad_value(self):
        messages = []
        scope = dict(parse_boolean_command_arguments=parse_boolean_command_arguments,
                     display_message=lambda *args: messages.append(args))
        exec(compile(ast.Module(body=[ingress.FUNCTIONS['_parse_boolean_command_arg']], type_ignores=[]), 'aurora2.py', 'exec'), scope)
        parse = scope['_parse_boolean_command_arg']
        self.assertEqual(parse([], 'SET_SHOW_AI_TEXT'), (None, False))
        self.assertEqual(parse(['off'], 'SET_SHOW_AI_TEXT'), (False, True))
        self.assertEqual(parse(['typo'], 'SET_SHOW_AI_TEXT'), (False, False))
        self.assertEqual(parse(['off', 'ignored'], 'SET_SHOW_AI_TEXT'), (False, False))
        self.assertEqual(len(messages), 2)

    def test_malformed_tail_rejects_whole_batch_and_handler_failure_stops_tail(self):
        fixture = ingress.RuntimeIngressTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        scope = fixture.scope
        scope['command_dispatch']['SET_SHOW_AI_TEXT'] = lambda args, user: False
        for command in ['SET_SHOW_AI_TEXT(off,ignored)', 'SET_SHOW_AI_TEXT(typo)']:
            result = scope['handle_commands']('UPDATE_NOTES(before); ' + command)
            self.assertFalse(result['success'])
            self.assertEqual(result['executed_commands'], [])
            self.assertEqual(fixture.executed, [])
        result = scope['handle_commands']('SET_SHOW_AI_TEXT(off); UPDATE_NOTES(after)')
        self.assertFalse(result['success'])
        self.assertEqual(result['blocked_commands'], ['UPDATE_NOTES(after)'])
        self.assertEqual(fixture.executed, [])


if __name__ == '__main__':
    unittest.main()
