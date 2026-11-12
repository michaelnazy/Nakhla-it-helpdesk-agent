"""Tests actual _draft() against the unmodified course JSON Schema.

No services started, no MCP writes, no network and no .env required.
"""
from __future__ import annotations

import ast
import json
import secrets
import types
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from v2_support import impacted_users, priority_for

ROOT = Path(__file__).resolve().parents[1]


def load_actual_draft():
    source = (ROOT / 'agent_backend.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_draft')
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    def reply(text, refs=None, *, tools=None, pending=None, result=None, workflow='answered'):
        return {'reply': text, 'citations': [{'id': x} for x in refs or []],
                'tool_calls': tools or [], 'pending_action': pending, 'state': workflow}
    namespace = {'Session': object, 'Any': object, 'secrets': secrets,
                 'impacted_users': impacted_users, 'priority_for': priority_for,
                 'DOCS': {'KB-015': {'meta': {}, 'text': ''}}, '_reply': reply}
    exec(compile(module, str(ROOT / 'agent_backend.py'), 'exec'), namespace)
    return namespace['_draft']


class TicketSchemaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / 'dataset' / 'schemas' / 'ticket.schema.json').read_text(encoding='utf-8'))
        cls.validator = Draft202012Validator(cls.schema)
        cls.draft = staticmethod(load_actual_draft())
        cls.employee = {'email': 'sara.mikhail@nakhla.example', 'department': 'Support',
                        'account_status': 'active'}

    def make_payload(self, question, subject):
        session = types.SimpleNamespace(pending=None)
        response = self.draft(session, subject, question, 'network_access', 'P2',
                              self.employee, ['KB-015'],
                              ['Reported the problem; troubleshooting steps not confirmed'], [])
        self.assertEqual(response['state'], 'awaiting_approval')
        self.assertIsNotNone(response['pending_action'])
        self.assertEqual(response['tool_calls'], [])
        return response['pending_action']['payload']

    def assert_schema_valid(self, payload):
        errors = sorted(self.validator.iter_errors(payload), key=lambda e: list(map(str, e.path)))
        self.assertEqual(errors, [], '\n'.join(f'{list(e.path)}: {e.message}' for e in errors))

    def test_CH10_exact_graph_subject_and_payload(self):
        question = ('Five people on our office floor cannot use the corporate Wi-Fi, '
                    'and work has stopped. Please create a support ticket.')
        subject = 'Network Access issue: ' + question[:100]
        self.assertEqual(len(subject), 122)
        payload = self.make_payload(question, subject)
        self.assertEqual(payload['category'], 'network_access')
        self.assertEqual(payload['priority'], 'P1')
        self.assertEqual(payload['affected_users'], 5)
        self.assertLessEqual(len(payload['subject']), 120)
        self.assert_schema_valid(payload)

    def test_long_graph_subject_always_bounded(self):
        q = 'The corporate Wi-Fi has been completely unavailable. Please open a support ticket.'
        payload = self.make_payload(q, 'Network Access issue: ' + ('Long details ' * 50))
        self.assert_schema_valid(payload)

    def test_regular_short_subject_unchanged(self):
        q = 'My office Wi-Fi does not work. Please create a support ticket.'
        subject = 'Network Access issue: Wi-Fi unavailable'
        payload = self.make_payload(q, subject)
        self.assertEqual(payload['subject'], subject)
        self.assert_schema_valid(payload)


if __name__ == '__main__':
    unittest.main()
