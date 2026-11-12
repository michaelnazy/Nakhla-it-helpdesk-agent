import json
import unittest
from v2_triage_graph import TriageDecision, ROUTES, parse_triage


def payload(**changes):
    base = {"intent":"knowledge", "topic":"vpn", "error_code":"nx-781", "confidence":0.91, "clarification_question":None}
    base.update(changes)
    return json.dumps(base)


class TriageSchemaTests(unittest.TestCase):
    def test_valid(self):
        d = parse_triage(payload())
        self.assertEqual(d.intent, "knowledge")
        self.assertEqual(d.error_code, "NX-781")

    def test_all_route_names_are_allowed(self):
        for route in ROUTES:
            self.assertEqual(parse_triage(payload(intent=route)).intent, route)

    def test_invalid_intent_rejected(self):
        with self.assertRaises(ValueError):
            parse_triage(payload(intent="create_ticket_directly"))

    def test_extra_tool_calls_rejected(self):
        d = json.loads(payload())
        d["tool_call"] = "create_ticket"
        with self.assertRaises(ValueError):
            parse_triage(json.dumps(d))

    def test_low_confidence_fails_closed(self):
        d = parse_triage(payload(intent="ticket_create", confidence=0.11))
        self.assertEqual(d.intent, "clarify")

    def test_invalid_error_code_removed(self):
        self.assertIsNone(parse_triage(payload(error_code="DROP TABLE USERS")).error_code)

    def test_fenced_json(self):
        self.assertEqual(parse_triage("```json\n" + payload() + "\n```").topic, "vpn")

    def test_non_json_rejected(self):
        with self.assertRaises(ValueError):
            parse_triage("create_ticket('admin')")

    def test_clarification_default(self):
        d = parse_triage(payload(intent="clarify", clarification_question=None))
        self.assertIn("clarify", d.clarification_question.lower())


if __name__ == "__main__":
    unittest.main()
