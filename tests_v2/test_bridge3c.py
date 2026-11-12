"""Exercise installed Phase 3c bridge with injected, deterministic graph routes."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from v2_backend_bridge import maybe_route
from v2_action_routes import explicit_new_ticket_request
from test_phase3c import FakeBackend, EMP


class BridgeContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend=FakeBackend()
        self.backend.vector_search=lambda q,top_k: []
        self.backend.mcp_call=AsyncMock(return_value={"ok": False})
        self.session=SimpleNamespace(pending=None,last_error='',last_category='',turns=[])
        self.tools=[]

    async def invoke_as(self, intent, question, employee=EMP):
        async def simulate_live(q, preflight, handlers):
            # This integration test exercises the real installed bridge closures.
            from ticket_memory_router import handle_ticket_query
            guard=await preflight(q)
            if guard is not None: return guard
            return await handlers[intent](q)
        with patch('v2_backend_bridge.run_live_graph',new=simulate_live), \
             patch('ticket_memory_router.handle_ticket_query',new_callable=AsyncMock) as reader:
            reader.return_value=None
            return await maybe_route(question,employee.get('email') if employee else '',
                                     employee,self.session,self.tools,self.backend)

    async def test_graph_ticket_create_reaches_approval_draft_not_writer(self):
        response=await self.invoke_as('ticket_create', 'Outlook calendar is failing. Please open a ticket.')
        self.assertEqual(response['state'],'langgraph_awaiting_approval')
        self.assertEqual(response['pending_action']['payload']['category'],'email_collab')
        self.assertEqual(len(self.backend.created),1)
        self.assertEqual(self.tools,[])

    async def test_model_hallucinated_ticket_create_denied(self):
        response=await self.invoke_as('ticket_create','How can I check my Wi-Fi status?')
        self.assertIsNone(response)
        self.assertEqual(self.backend.created,[])

    async def test_model_misroutes_explicit_ticket_to_knowledge_fallback(self):
        response=await self.invoke_as('knowledge','Please open a support ticket for my broken laptop.')
        self.assertIsNone(response)
        self.assertEqual(self.backend.created,[])

    async def test_verified_employee_is_required_for_ticket_create(self):
        response=await self.invoke_as('ticket_create','Please open a ticket for my computer.',None)
        self.assertEqual(response['state'],'needs_verification')
        self.assertEqual(self.backend.created,[])

    async def test_error_code_ticket_defers_to_legacy_verified_handler(self):
        response=await self.invoke_as('ticket_create','NakhlaConnect NX-503. Open a ticket.')
        self.assertIsNone(response)
        self.assertEqual(self.backend.created,[])


if __name__=='__main__':
    unittest.main()
