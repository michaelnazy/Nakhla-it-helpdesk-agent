"""Zero-external-service test of the REAL backend approval handler.

Extracts only its original class/function AST so the test needs neither MCP
server nor OpenRouter. Verifies replay semantics and writes using a fake MCP.
"""
import ast
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import re
import unittest

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]


def make_runtime():
    source = (ROOT / 'agent_backend.py').read_text(encoding='utf-8')
    module = ast.parse(source)
    names = {'Session', 'ApproveRequest', '_created_ticket_id', 'approve'}
    nodes = [n for n in module.body if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert len(nodes) == 4, [n.name for n in nodes]
    app = FastAPI()
    calls = []
    async def fake_mcp(name, args):
        calls.append((name, args))
        return {'ok': True, 'ticket': {'ticket_id': 'IT-2001'}}
    ns = dict(app=app, asyncio=asyncio, dataclass=dataclass, field=field,
              Any=object, BaseModel=BaseModel, Field=Field,
              JSONResponse=JSONResponse, re=re, WRITE_ENABLED=True,
              logger=__import__('logging').getLogger('test'),
              sessions={}, mcp_call=fake_mcp, calls=calls)
    def reply(message, refs=None, *, tools=None, pending=None, result=None, workflow='answered'):
        value = {'reply': message, 'pending_action': pending, 'tool_calls': tools or [], 'state': workflow, 'citations': []}
        if result is not None:
            value['result'] = result
        return value
    ns['_reply'] = reply
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'agent_backend.py'), 'exec'), ns)
    return ns


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_approval_replay_does_not_write_twice(self):
        ns = make_runtime()
        sess = ns['Session']()
        sess.pending = {'action_id': 'action123456', 'payload': {'subject': 'demo'}}
        ns['sessions']['s1'] = sess
        req = ns['ApproveRequest'](session_id='s1', action_id='action123456', approved=True)
        first = await ns['approve'](req)
        again = await ns['approve'](req)
        self.assertEqual(first, again)
        self.assertEqual(first['result']['ticket_id'], 'IT-2001')
        self.assertEqual(len(ns['calls']), 1)
        self.assertEqual(ns['calls'][0][1]['idempotency_key'], 'action123456')

    async def test_rejection_replay_has_zero_writes(self):
        ns = make_runtime()
        sess = ns['Session']()
        sess.pending = {'action_id': 'action123456', 'payload': {}}
        ns['sessions']['s2'] = sess
        req = ns['ApproveRequest'](session_id='s2', action_id='action123456', approved=False)
        first = await ns['approve'](req)
        again = await ns['approve'](req)
        self.assertEqual(first, again)
        self.assertEqual(len(ns['calls']), 0)
        self.assertEqual(first['state'], 'rejected')

    async def test_changed_decision_after_rejection_still_conflicts(self):
        ns = make_runtime()
        sess = ns['Session']()
        sess.pending = {'action_id': 'action123456', 'payload': {}}
        ns['sessions']['s3'] = sess
        await ns['approve'](ns['ApproveRequest'](session_id='s3', action_id='action123456', approved=False))
        result = await ns['approve'](ns['ApproveRequest'](session_id='s3', action_id='action123456', approved=True))
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(len(ns['calls']), 0)

    async def test_tool_failure_is_cached_without_fabricated_ticket_id(self):
        ns = make_runtime()
        async def error_mcp(name, args):
            ns['calls'].append((name,args))
            return {'ok': False, 'error': {'code': 'service_unavailable'}}
        ns['mcp_call'] = error_mcp
        sess = ns['Session']()
        sess.pending = {'action_id': 'action123456', 'payload': {}}
        ns['sessions']['s4'] = sess
        req = ns['ApproveRequest'](session_id='s4', action_id='action123456', approved=True)
        first = await ns['approve'](req)
        second = await ns['approve'](req)
        self.assertEqual(first, second)
        self.assertEqual(first['state'], 'create_failed')
        self.assertNotIn('result', first)
        self.assertEqual(len(ns['calls']), 1)

    async def test_disabled_writes_still_disabled_on_replay(self):
        ns = make_runtime()
        ns['WRITE_ENABLED'] = False
        sess = ns['Session']()
        sess.pending = {'action_id': 'action123456', 'payload': {}}
        ns['sessions']['s5'] = sess
        req = ns['ApproveRequest'](session_id='s5', action_id='action123456', approved=True)
        first = await ns['approve'](req)
        again = await ns['approve'](req)
        self.assertIsInstance(first, JSONResponse)
        self.assertEqual(first.status_code, 403)
        self.assertIs(first, again)
        self.assertEqual(len(ns['calls']), 0)


if __name__ == '__main__':
    unittest.main()
