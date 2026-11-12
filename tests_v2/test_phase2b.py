"""New regression tests for genuine source-grounded answers (not kit fixtures)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v2_support import policy_first, choose_reported_error_evidence, general_answer


class PolicyRegressions(unittest.TestCase):
    def test_sms_prohibition_uses_unambiguous_language(self):
        r = policy_first('Can IT send me an SMS code instead of NakhlaKey?', {'department': 'Engineering'})
        self.assertIsNotNone(r)
        self.assertEqual(r['kind'], 'answer')
        self.assertIn('not allowed', r['text'])
        self.assertIn('SP-002', r['refs'])

    def test_phone_password_reset_uses_higher_priority_policy(self):
        r = policy_first('Could the service desk reset my NakhlaID password over the phone?',
                         {'department': 'Support'})
        self.assertEqual(r['kind'], 'answer')
        self.assertEqual(r['refs'][:2], ['SP-001', 'KB-004'])
        self.assertIn('not allowed', r['text'])
        self.assertIn('https://id.nakhla.example/reset', r['text'])
        self.assertIn('manager approval', r['text'])

    def test_password_reset_rephrasing(self):
        r = policy_first('Can IT support change my password via chat?', {'department': 'Sales'})
        self.assertIsNotNone(r)
        self.assertIn('SP-001', r['refs'])

    def test_self_service_phone_browser_is_not_forbidden(self):
        r = policy_first('Can I use my phone to reset my own NakhlaID password?',
                         {'department': 'Sales'})
        self.assertIsNone(r)

    def test_existing_contractor_guard_still_works(self):
        r = policy_first('Can you create a VPN ticket? I am a contractor',
                         {'department': 'Contractors'})
        self.assertEqual(r['kind'], 'answer')
        self.assertIn('SP-002', r['refs'])


class ErrorMessageEvidence(unittest.TestCase):
    def setUp(self):
        self.docs = {
            'KB-008': {
                'meta': {'status': 'current', 'authoritative': True},
                'text': '| `NID-512` | "This app is not assigned to you" | Request it at `https://access.nakhla.example` (KB-011). |',
            },
            'KB-011': {
                'meta': {'status': 'current', 'authoritative': True},
                'text': 'Access permissions and access requests. Open https://access.nakhla.example to request access.',
            },
        }

    def test_code_free_crm_assignment_message_picks_exact_guide(self):
        r = choose_reported_error_evidence(
            'NakhlaCRM says this app is not assigned to me. Where do I request access?', self.docs)
        self.assertIsNotNone(r)
        self.assertEqual(r['document_id'], 'KB-008')
        answer, refs = general_answer(r)
        self.assertEqual(refs, ['KB-008'])
        self.assertIn('access.nakhla.example', answer)

    def test_phrase_first_is_grounded_even_if_another_guide_covers_access(self):
        r = choose_reported_error_evidence(
            'NakhlaPeople shows this app is not assigned to me.', self.docs)
        self.assertEqual(r['document_id'], 'KB-008')

    def test_no_match_when_phrase_not_in_current_docs(self):
        r = choose_reported_error_evidence('App says your files are gone forever.', self.docs)
        self.assertIsNone(r)

    def test_deprecated_article_never_used(self):
        docs = dict(self.docs)
        docs['KB-999'] = {'meta': {'status': 'deprecated', 'authoritative': True},
                          'text': 'Fake app says your files are gone forever.'}
        self.assertIsNone(choose_reported_error_evidence('Fake app says your files are gone forever.', docs))

    def test_no_error_report_uses_semantic_route(self):
        r = choose_reported_error_evidence('Where do I request CRM access?', self.docs)
        self.assertIsNone(r)


if __name__ == '__main__':
    unittest.main()
