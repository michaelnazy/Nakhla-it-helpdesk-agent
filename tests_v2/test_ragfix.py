"""Tests against actual approved KB docs, no OpenRouter credentials needed."""
import asyncio
import json
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import v2_support
import v2_backend_bridge


def load_real_docs():
    docs={}
    for f in sorted((ROOT/'dataset'/'knowledge_base').glob('*.md')):
        pieces=f.read_text(encoding='utf-8').split('---',2)
        if len(pieces)<3:continue
        meta=yaml.safe_load(pieces[1]) or {}
        docs[meta['id']]={'id':meta['id'],'meta':meta,'text':pieces[2]}
    return docs

class NormalizationTests(unittest.TestCase):
    def test_wifi_spellings_keep_word(self):
        for word in ('Wi-Fi','WiFi','wi fi','wireless'):
            self.assertIn('wifi',v2_support._terms('How do I set up office '+word+'?'))
    def test_normal_wifi_semantic_chunk(self):
        docs=load_real_docs()
        text=docs['KB-003']['text'][:900]
        match=[{'document_id':'KB-003','text':text,'score':0.57}]
        ev=v2_support.choose_general_evidence('How do I set up office Wi-Fi?',match,docs)
        self.assertIsNotNone(ev)
        self.assertEqual(ev['document_id'],'KB-003')
    def test_catalog_finds_current_wifi_guide_without_embeddings(self):
        docs=load_real_docs()
        ev=v2_support.choose_catalog_evidence('How do I set up office Wi-Fi?',docs)
        self.assertEqual(ev['document_id'],'KB-003')
        self.assertIn('Nakhla-Corp',ev['text'])
    def test_catalog_does_not_return_random_article(self):
        docs=load_real_docs()
        self.assertIsNone(v2_support.choose_catalog_evidence('Why is my spaceship quantum jellyfish?', docs))
    def test_no_single_token_catalog_match(self):
        docs=load_real_docs()
        self.assertIsNone(v2_support.choose_catalog_evidence('Wi-Fi?',docs))
    def test_deprecated_or_unauthoritative_never_selected(self):
        docs=load_real_docs()
        target=docs['KB-003']
        for edit in ({'status':'deprecated'},{'authoritative':False}):
            modified=dict(target['meta'],**edit)
            spoof={'KB-003':{**target,'meta':modified}}
            self.assertIsNone(v2_support.choose_catalog_evidence('How do I set up office Wi-Fi?',spoof))
    def test_ambiguity_does_not_guess(self):
        docs=load_real_docs()
        both={a:docs['KB-003'] for a in ('KB-003','KB-888')}
        self.assertIsNone(v2_support.choose_catalog_evidence('How do I set up office Wi-Fi?',both))

class BridgeSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_langgraph_knowledge_handler_gives_grounded_answer(self):
        docs={'KB-003':load_real_docs()['KB-003']}
        session=SimpleNamespace(last_error='',last_category='',turns=[])
        lookup=[]
        async def memory(*args,**kwargs):return None
        async def fake_flow(question, preflight, handlers, model_fn=None):
            self.assertIsNone(await preflight(question))
            return await handlers['knowledge'](question)
        def reply(msg,citations=None,tools=None,workflow='unknown',**kw):
            return {'reply':msg,'citations':citations or [], 'tool_calls':tools or [], 'pending_action':None,'state':workflow}
        def vector_search(*args,**kwargs):return []  # prove safe recovery when embedding misses article
        backend=SimpleNamespace(CODE=re.compile(r'\bNX-\d+\b'),DOCS=docs,vector_search=vector_search,
                                _reply=reply,mcp_call=lambda *args: (_ for _ in ()).throw(AssertionError('unwanted MCP')))
        fake_router=SimpleNamespace(handle_ticket_query=memory)
        with patch.dict(sys.modules,{'ticket_memory_router':fake_router}):
            with patch.object(v2_backend_bridge,'run_live_graph',fake_flow):
                response=await v2_backend_bridge.maybe_route('How do I set up office Wi-Fi?',
                            'tariq.hamdan@nakhla.example',{},session,lookup,backend)
        self.assertEqual(response['state'],'langgraph_rag_answer')
        self.assertEqual(response['citations'],['KB-003'])
        self.assertIn('Nakhla-Corp',response['reply'])
        self.assertEqual(response['pending_action'],None)
        self.assertEqual(lookup,[])

if __name__=='__main__':unittest.main()
