import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2_support import impacted_users, executive, contractor, priority_for, policy_first, choose_general_evidence, general_answer

class PolicyTests(unittest.TestCase):
    def test_impact_count(self):
        self.assertEqual(impacted_users('4 users have lost access'), 4)
        self.assertEqual(impacted_users('It affects four people'), 4)
        self.assertEqual(impacted_users('3 colleagues affected'), 3)
        self.assertEqual(impacted_users('My phone is broken'), 1)
    def test_executive_ticket_p1(self):
        self.assertEqual(priority_for('P4', {'department': 'Executive Office'}, 'software', 1), 'P1')
        self.assertEqual(priority_for('P3', {'department': 'Support'}, 'network_access', 5), 'P1')
        self.assertEqual(priority_for('P2', {'department': 'Finance'}, 'security', 1, 'Finance VPN NX-403'), 'P2')
    def test_contractor_vpn_is_refused(self):
        r=policy_first('Please open a VPN ticket for me, NX-403', {'department': 'Contractors'})
        self.assertEqual(r['kind'], 'answer')
        self.assertIn('must not be created', r['text'])
        self.assertIn('SP-002',r['refs'])
    def test_sms_prohibited_even_if_old_faq_suggests_it(self):
        r=policy_first('Could I get an SMS MFA code because my phone is at home?', {'department':'Sales'})
        self.assertEqual(r['kind'],'answer')
        self.assertIn('prohibited',r['text'])
    def test_sms_code_request_without_mfa_keyword(self):
        r=policy_first('Could you send me an SMS code to sign in?', {'department':'Sales'})
        self.assertEqual(r['kind'],'answer')
        self.assertIn('SP-002',r['refs'])
    def test_phone_home_backup_code(self):
        r=policy_first('I left my phone at home, how to log in?', {'department':'Support'})
        self.assertEqual(r['kind'],'answer')
        self.assertIn('backup codes',r['text'])
    def test_lost_nakhlakey_is_security_draft(self):
        r=policy_first('My phone with NakhlaKey was stolen', {'department':'Engineering'})
        self.assertEqual(r['kind'],'draft')
        self.assertEqual(r['priority'],'P1')
    def test_personal_laptop_block(self):
        r=policy_first('Can I use a personal laptop to access NakhlaConnect VPN?', {'department':'Engineering'})
        self.assertEqual(r['kind'],'answer')
        self.assertIn('Personal laptops',r['text'])
    def test_unrelated_untouched(self):
        self.assertIsNone(policy_first('My printer is not working', {'department': 'Support'}))

class SessionTests(unittest.TestCase):
    def test_new_topic_clears_stale_nx_code(self):
        from v2_support import topic_shift
        self.assertTrue(topic_shift('How do guests get the wifi access code?', 'NX-781'))
        self.assertFalse(topic_shift('I tried those steps, still not working', 'NX-781'))
    def test_normal_question_no_old_error(self):
        from v2_support import topic_shift
        self.assertFalse(topic_shift('How do I get guest wifi?', ''))

class RagTests(unittest.TestCase):
    def setUp(self):
        self.docs={
          'KB-003': {'meta': {'status':'current','authoritative':True,'title':'Office wifi troubleshooting','tags':['wifi','visitors']},'text':'...'},
          'KB-017': {'meta': {'status':'current','authoritative':False,'title':'Unofficial FAQ','tags':['wifi']},'text':'...'},
          'KB-001': {'meta': {'status':'deprecated','authoritative':True,'title':'Old wifi guide'},'text':'...'},
        }
    def test_general_question_finds_current_guide(self):
        hits=[{'document_id':'KB-003','score':.55,'text':'Visitors use Nakhla-Guest wifi; obtain access from reception.'}]
        chosen=choose_general_evidence('How can visitors get wifi?', hits,self.docs)
        self.assertEqual(chosen['document_id'],'KB-003')
        text,refs=general_answer(chosen)
        self.assertEqual(refs,['KB-003'])
        self.assertIn('Nakhla-Guest',text)
    def test_no_invention_for_low_confidence(self):
        hits=[{'document_id':'KB-003','score':.19,'text':'Visitors use wifi'}]
        self.assertIsNone(choose_general_evidence('What is the price of airplane tickets?',hits,self.docs))
        self.assertEqual(general_answer(None)[1],[])
    def test_unsupported_doc_excluded(self):
        hits=[{'document_id':'KB-017','score':.9,'text':'Visitors may get wifi via SMS'}, {'document_id':'KB-001','score':.9,'text':'Visitors get wifi'}]
        self.assertIsNone(choose_general_evidence('How can visitors get wifi?',hits,self.docs))
    def test_unrelated_even_with_high_score(self):
        hits=[{'document_id':'KB-003','score':.70,'text':'Office Wi-Fi networks and visitors'}]
        self.assertIsNone(choose_general_evidence('How can I obtain a private cloud invoice?',hits,self.docs))

if __name__ == '__main__': unittest.main()
