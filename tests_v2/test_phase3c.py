"""Phase 3c contracts, no live API, network, or simulator modifications."""
import asyncio
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from v2_action_routes import (explicit_new_ticket_request, ticket_category,
                               prepare_ticket, verified_incident, grounded_policy)


class FakeBackend:
    CODE = re.compile(r'\b(?:NX|NID|SWC|CRM|HW)-\d{3,5}\b', re.I)
    DOCS = {'KB-015': {'id': 'KB-015', 'meta': {'title': 'Ticket priority'}, 'text': 'Priority guide'}}
    def __init__(self):
        self.created = []
    def _reply(self, text, refs=None, *, tools=None, pending=None, workflow='answered'):
        return {'reply': text, 'citations': [{'id': ref} for ref in (refs or [])],
                'tool_calls': tools or [], 'pending_action': pending, 'state': workflow}
    def _draft(self, session, subject, description, category, priority, employee, refs, attempted, tools):
        payload={'subject': subject, 'description': description,
                 'category': category, 'priority': priority,
                 'affected_users': __import__('v2_support').impacted_users(description)}
        self.created.append(payload)
        session.pending = {'type':'create_ticket','action_id':'safe-request-012345', 'payload':payload}
        return self._reply('Review draft; no ticket exists.',refs,tools=tools,
                           pending=session.pending,workflow='awaiting_approval')
    @staticmethod
    def _already_tried(q):
        return 'already' in q.lower() or 'tried' in q.lower()

EMP = {'email':'sara.mikhail@nakhla.example','department':'Support','account_status':'active'}


class SafeDraftTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_request_creates_pending_draft_no_mcp_write(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        answer=await prepare_ticket('Five employees cannot reach Wi-Fi; please open a support ticket.',
                                    EMP,session,[],backend)
        self.assertEqual(answer['state'],'langgraph_awaiting_approval')
        self.assertEqual(answer['pending_action']['type'],'create_ticket')
        self.assertEqual(backend.created[0]['category'],'network_access')
        self.assertEqual(backend.created[0]['affected_users'],5)
        self.assertEqual(backend.created[0]['priority'],'P1')
        self.assertNotIn('result', answer)
        self.assertEqual(answer['tool_calls'],[])
    async def test_executive_p1(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        executive={**EMP,'department':'Executive Office','vip':True}
        answer=await prepare_ticket('My company laptop broke. Please create a ticket.',executive,session,[],backend)
        self.assertEqual(answer['pending_action']['payload']['priority'],'P1')
        self.assertEqual(answer['pending_action']['payload']['category'],'hardware')
    async def test_requires_verified_employee(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        answer=await prepare_ticket('Please open a ticket for my email.',None,session,[],backend)
        self.assertEqual(answer['state'],'needs_verification')
        self.assertEqual(backend.created,[])
    async def test_disallowed_account_no_draft(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        answer=await prepare_ticket('Open a ticket for my laptop.',{**EMP,'account_status':'disabled'},session,[],backend)
        self.assertIsNone(answer['pending_action'])
        self.assertEqual(backend.created,[])
    async def test_vpn_and_error_code_defer_to_verified_legacy(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        for q in ('NakhlaConnect NX-503. Please open a ticket',
                  'My VPN is failing, create a ticket.',
                  'SWC-2001 install failed, raise a ticket.'):
            self.assertIsNone(await prepare_ticket(q,EMP,session,[],backend),q)
        self.assertEqual(backend.created,[])
    async def test_nonrequest_must_not_become_draft(self):
        backend=FakeBackend(); session=SimpleNamespace(pending=None)
        for q in ('Show my open tickets', 'How do I access Nakhla Wi-Fi?',
                  'Do not open a ticket for this problem'):
            self.assertIsNone(await prepare_ticket(q,EMP,session,[],backend),q)
        self.assertEqual(backend.created,[])


class IntentTests(unittest.TestCase):
    def test_new_ticket_phrasings(self):
        for q in ('Open a security ticket please', 'Please prepare a support ticket for my approval',
                  'Could you create a ticket for Outlook?', 'Please raise a new ticket about this issue', 'I need a ticket for the projector'):
            self.assertTrue(explicit_new_ticket_request(q),q)
    def test_ticket_read_and_denial(self):
        for q in ('Show my open tickets', 'List previous tickets', 'Don\'t create a ticket',
                  'I do not want to open a ticket', 'I do not want a ticket', 'How do I open a support ticket?'):
            self.assertFalse(explicit_new_ticket_request(q),q)
    def test_classifications(self):
        self.assertEqual(ticket_category('Five users Wi-Fi is down')[0],'network_access')
        self.assertEqual(ticket_category('Outlook calendar is broken')[0],'email_collab')
        self.assertEqual(ticket_category('My laptop screen broke')[0],'hardware')


class IncidentTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_verified_incident_is_returned(self):
        backend=FakeBackend(); tools=[]
        backend.WORKFLOW=SimpleNamespace(ainvoke=AsyncMock(return_value={
            'incident_applicability':{'status':'affected'}, 'source_validation':{'passed':True},
            'verification':{'passed':True}, 'source_refs':['INC-2207'],
            'cited_answer':'Verified incident: GW-1'}))
        answer=await verified_incident('Our VPN shows NX-503',EMP,tools,backend)
        self.assertEqual(answer['state'],'langgraph_verified_incident')
        self.assertEqual(answer['citations'],[{'id':'INC-2207'}])
        self.assertEqual(tools,[{'tool':'get_service_status','ok':True}])
    async def test_unverified_incident_never_asserted(self):
        backend=FakeBackend(); backend.WORKFLOW=SimpleNamespace(ainvoke=AsyncMock(return_value={
            'incident_applicability':{'status':'affected'}, 'source_validation':{'passed':False},
            'verification':{'passed':True},'source_refs':['INC-2207'], 'cited_answer':'Bad'}))
        self.assertIsNone(await verified_incident('Our VPN shows NX-503',EMP,[],backend))
    async def test_other_codes_use_legacy(self):
        backend=FakeBackend(); backend.WORKFLOW=SimpleNamespace(ainvoke=AsyncMock())
        self.assertIsNone(await verified_incident('NX-112 outage',EMP,[],backend))
        backend.WORKFLOW.ainvoke.assert_not_awaited()


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_grounded_policy_uses_approved_policy_doc(self):
        backend=FakeBackend()
        backend.DOCS={'SP-002': {'id':'SP-002','meta':{'title':'NakhlaKey SMS voice MFA security policy',
                         'status':'current','authoritative':True,'tags':['MFA','SMS']},
                         'text':'# NakhlaKey SMS voice MFA security policy\nSMS MFA codes are not allowed.'}}
        backend.vector_search=lambda q,top_k:[{'document_id':'SP-002','score':0.90,
            'text':'# NakhlaKey SMS voice MFA security policy\nSMS MFA codes are not allowed.'}]
        with patch('v2_action_routes.choose_general_evidence') as chooser:
            chooser.return_value={'document_id':'SP-002','text':'SMS MFA codes are not allowed.','score':0.9}
            answer=await grounded_policy('May we use SMS codes?',[],backend)
        self.assertEqual(answer['state'],'langgraph_policy_grounded')
        self.assertEqual(answer['citations'],[{'id':'SP-002'}])
    async def test_non_policy_document_not_returned_as_policy(self):
        backend=FakeBackend()
        backend.vector_search=lambda q,top_k: []
        with patch('v2_action_routes.choose_general_evidence', return_value={
            'document_id':'KB-004','text':'Password self-service help','score':0.9}):
            self.assertIsNone(await grounded_policy('Is phone reset allowed?',[],backend))
    async def test_policy_node_never_executes_ticket(self):
        backend=FakeBackend(); backend.vector_search=lambda q,top_k: []
        self.assertIsNone(await grounded_policy('Please open a security ticket',[],backend))


class InstalledBridgeTests(unittest.TestCase):
    def test_current_bridge_compiles_and_stays_read_only(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        source=(root/'v2_backend_bridge.py').read_text(encoding='utf-8')
        compile(source,'v2_backend_bridge.py','exec')
        for forbidden in ('mcp_call("create_ticket"', "mcp_call('create_ticket'", 'mcp_call("add_ticket_note"', "mcp_call('add_ticket_note'"):
            self.assertNotIn(forbidden,source)
        for route in ("'policy': policy", "'incident': incident", "'ticket_create': ticket_create"):
            self.assertIn(route,source)

try:
    import langgraph  # noqa
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

@unittest.skipUnless(LANGGRAPH_AVAILABLE, 'LangGraph is not installed')
class ConditionalGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_routes_ticket_create_only_to_draft_handler(self):
        from v2_live_flow import build_live_graph
        hits=[]
        async def preflight(q): return None
        async def model(q):
            return '{"intent":"ticket_create","topic":"network","error_code":null,"confidence":0.96,"clarification_question":null}'
        async def draft(q): hits.append('draft'); return {'reply':'review', 'pending_action':{'action_id':'x'}}
        async def read(q): hits.append('read'); return None
        graph=build_live_graph(preflight,{'ticket_create':draft,'ticket_read':read},model)
        result=await graph.ainvoke({'question':'Please open a ticket for Wi-Fi'})
        self.assertEqual(hits,['draft'])
        self.assertEqual(result['response']['reply'],'review')

if __name__ == '__main__':
    unittest.main()
