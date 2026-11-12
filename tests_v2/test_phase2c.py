"""Additional independent tests for source-backed security and escalation rules.

These are unit/contract checks; they do not replace live MCP/API evaluation.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ticket_memory_router import _classify
from v2_support import policy_first, impacted_users, priority_for

SARA = {'email':'sara.mikhail@nakhla.example', 'department':'Sales'}


class TicketIntentRouting(unittest.TestCase):
    def test_create_security_ticket_not_misread_as_history(self):
        self.assertEqual(_classify('I typed my work password into a fake login page. Please open a security ticket now.')[0], '')

    def test_security_ticket_rephrasing(self):
        for sentence in ('Please create a security ticket for me', 'Could you raise a new incident ticket?',
                         'Open a network ticket for the office Wi-Fi', 'Log a security ticket'):
            with self.subTest(sentence=sentence):
                self.assertEqual(_classify(sentence)[0], '')

    def test_existing_ticket_reads_preserved(self):
        cases = {
            'What are my open tickets?':'open',
            'Show my ticket history':'history',
            'Show details of IT-1002':'details',
            'Have I had NX-781 before?':'similar',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_classify(text)[0], expected)


class SourceBasedSecurityPolicy(unittest.TestCase):
    def test_credential_submission_draft_p1(self):
        r = policy_first('I typed my work password on a fake login page. Please open a security ticket now.', SARA)
        self.assertEqual(r['kind'], 'draft')
        self.assertEqual((r['category'],r['priority']), ('security','P1'))
        self.assertIn('SP-001', r['refs'])

    def test_fake_page_report_without_ticket_is_safety_advice(self):
        r = policy_first('I entered my credentials in a suspicious website, what should I do?', SARA)
        self.assertEqual(r['kind'], 'answer')
        self.assertIn('SP-001',r['refs'])
        self.assertIn('Reset your', r['text'])

    def test_unsolicited_mfa_prompt_is_security(self):
        r = policy_first('NakhlaKey is showing prompts I did not start. What should I do?', SARA)
        self.assertEqual(r['kind'], 'answer')
        self.assertIn('SP-001',r['refs'])

    def test_phishing_email_without_credentials_does_not_claim_compromise(self):
        r = policy_first('I saw a suspicious email with a fake login page but did not enter my password.', SARA)
        self.assertIsNone(r)

    def test_explicitly_denied_credential_submission_is_not_compromise(self):
        self.assertIsNone(policy_first('I never entered my password on the suspicious fake site.', SARA))

    def test_normal_mail_to_external_allowed_by_rule(self):
        self.assertIsNone(policy_first('Can I send a normal email to a customer at Gmail?',SARA))

    def test_automatic_external_mail_forwarding_blocked(self):
        r = policy_first('How do I set up automatic Nakhla Mail forwarding to my personal Gmail inbox?', SARA)
        self.assertEqual(r['kind'],'answer')
        self.assertIn('KB-014',r['refs'])
        self.assertIn('blocked',r['text'])

    def test_regular_forward_to_colleague_not_blocked(self):
        self.assertIsNone(policy_first('How do I manually forward one email to my work colleague?', SARA))

    def test_unexplained_daily_lockouts_escalated(self):
        r=policy_first('My NakhlaID account was locked out three separate times today, and I do not know why. What should I do?',SARA)
        self.assertEqual(r['kind'],'answer')
        self.assertIn('SP-001', r['refs'])
        self.assertIn('security',r['text'])
        self.assertIn('P2',r['text'])

    def test_repeated_unexplained_lockout_ticket_is_p2(self):
        r=policy_first('My NakhlaID locked three times today for no reason, please create a ticket.',SARA)
        self.assertEqual(r['kind'], 'draft')
        self.assertEqual((r['category'], r['priority']), ('security', 'P2'))

    def test_known_cause_lockouts_do_not_claim_attack(self):
        self.assertIsNone(policy_first('My account locked three times today because I kept typing an old password.',SARA))

    def test_affected_users_and_priority(self):
        text='Five people on our office floor cannot use corporate Wi-Fi, and work has stopped.'
        n=impacted_users(text)
        self.assertEqual(n, 5)
        self.assertEqual(priority_for('P2', SARA,'network_access',n,text), 'P1')


if __name__ == '__main__':
    unittest.main()
