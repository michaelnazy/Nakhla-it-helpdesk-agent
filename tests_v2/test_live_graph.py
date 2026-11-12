"""Integration contract for phase 3b graph. No real API or model calls."""
import unittest
from v2_live_flow import build_live_graph

try:
    import langgraph  # noqa: F401
    AVAILABLE=True
except ImportError:
    AVAILABLE=False


def json_for(intent, confidence=0.96):
    return ('{"intent":"'+intent+'","topic":"general",'
            '"error_code":null,"confidence":'+str(confidence)+',"clarification_question":null}')


@unittest.skipUnless(AVAILABLE, 'langgraph installed in project .venv')
class LiveGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_preflight_short_circuits_without_llm(self):
        hits=[]
        async def preflight(q):
            hits.append('guard')
            return {'reply':'Blocked by mandatory policy'}
        async def model(q):
            hits.append('llm')
            return json_for('knowledge')
        graph=build_live_graph(preflight, {}, model)
        actual=await graph.ainvoke({'question':'forward mail to private gmail'})
        self.assertEqual(actual['response']['reply'], 'Blocked by mandatory policy')
        self.assertEqual(hits,['guard'])

    async def test_dynamic_knowledge_handler_is_reached(self):
        hits=[]
        async def preflight(q): return None
        async def model(q): return json_for('knowledge')
        async def knowledge(q):
            hits.append(q)
            return {'reply':'KB-015 procedure', 'citations':[{'id':'KB-015'}]}
        graph=build_live_graph(preflight, {'knowledge':knowledge}, model)
        result=await graph.ainvoke({'question':'Help with Wi-Fi'})
        self.assertEqual(hits, ['Help with Wi-Fi'])
        self.assertEqual(result['response']['citations'][0]['id'], 'KB-015')
        self.assertEqual(result['status'],'graph_answered')

    async def test_ticket_read_runs_only_allowed_read_handler(self):
        hits=[]
        async def preflight(q): return None
        async def model(q): return json_for('ticket_read')
        async def read(q): hits.append('read'); return {'reply':'verified owned ticket'}
        async def kb(q): hits.append('kb'); return None
        graph=build_live_graph(preflight, {'ticket_read':read,'knowledge':kb}, model)
        result=await graph.ainvoke({'question':'My last support ticket'})
        self.assertEqual(result['response']['reply'],'verified owned ticket')
        self.assertEqual(hits,['read'])

    async def test_ticket_create_does_not_invoke_any_write_tool(self):
        hits=[]
        async def preflight(q): return None
        async def model(q): return json_for('ticket_create')
        async def knowledge(q): hits.append('knowledge'); return {'reply':'unsafe'}
        graph=build_live_graph(preflight, {'knowledge':knowledge}, model)
        result=await graph.ainvoke({'question':'Create ticket'})
        self.assertIsNone(result.get('response'))
        self.assertEqual(result['route'],'legacy')
        self.assertEqual(hits,[])

    async def test_model_fails_fallback_without_write(self):
        async def preflight(q): return None
        async def broken(q): raise RuntimeError('No LLM')
        graph=build_live_graph(preflight, {}, broken)
        result=await graph.ainvoke({'question':'create a new ticket'})
        self.assertIsNone(result.get('response'))
        self.assertEqual(result['route'],'legacy')
        self.assertEqual(result['triage_status'],'model_unavailable')

    async def test_low_confidence_action_falls_back(self):
        async def preflight(q): return None
        async def model(q): return json_for('ticket_read', 0.65)
        async def read(q): return {'reply':'should not show'}
        graph=build_live_graph(preflight, {'ticket_read':read}, model)
        result=await graph.ainvoke({'question':'Which ticket?'})
        self.assertIsNone(result.get('response'))
        self.assertEqual(result['triage_status'],'low_action_confidence')

    async def test_unhandled_policy_route_falls_back_safely(self):
        async def preflight(q): return None
        async def model(q): return json_for('policy')
        graph=build_live_graph(preflight, {}, model)
        result=await graph.ainvoke({'question':'Is it allowed?'})
        self.assertIsNone(result.get('response'))
        self.assertEqual(result['route'],'legacy')


class StaticContractTests(unittest.TestCase):
    def test_no_direct_writer_access_in_bridge(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parent.parent/'v2_backend_bridge.py').read_text()
        self.assertNotIn('mcp_call("create_ticket"', source)
        self.assertNotIn("mcp_call('create_ticket'", source)
        self.assertNotIn('mcp_call("add_ticket_note"', source)


if __name__=='__main__':
    unittest.main()
