import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1] / "CTM Daily Sync"
sys.path.insert(0, str(MODULE_DIR))

from ctm_custom_fields import enrich_call_custom_fields  # noqa: E402


class CtmCustomFieldTests(unittest.TestCase):
    def test_extracts_preferred_custom_fields(self):
        call = {
            "custom_fields": {
                "valid_lead": "yes",
                "lead_summary": "Booked inspection",
                "is_spam": "no",
            }
        }

        enrich_call_custom_fields(call)

        self.assertIs(call["valid_lead"], True)
        self.assertEqual(call["valid_lead_raw"], "yes")
        self.assertEqual(call["lead_summary"], "Booked inspection")
        self.assertIs(call["is_spam"], False)
        self.assertEqual(call["is_spam_raw"], "no")

    def test_contact_fields_are_used_when_custom_fields_are_absent(self):
        call = {
            "contact": {
                "custom_fields": {
                    "valid_lead": "1",
                    "lead_summary": "Qualified from contact",
                    "is_spam": "0",
                }
            }
        }

        enrich_call_custom_fields(call)

        self.assertIs(call["valid_lead"], True)
        self.assertEqual(call["lead_summary"], "Qualified from contact")
        self.assertIs(call["is_spam"], False)

    def test_score_fields_are_used_after_contact_fields(self):
        call = {
            "contact": {"valid_lead": "false"},
            "score": {
                "custom_fields": {
                    "valid_lead": "true",
                    "lead_summary": "Score summary",
                    "is_spam": "false",
                }
            },
        }

        enrich_call_custom_fields(call)

        self.assertIs(call["valid_lead"], False)
        self.assertEqual(call["valid_lead_raw"], "false")
        self.assertEqual(call["lead_summary"], "Score summary")
        self.assertIs(call["is_spam"], False)

    def test_falls_back_to_arbitrary_nested_exact_field_names(self):
        call = {
            "details": [
                {
                    "fields": [
                        {"name": "valid_lead", "value": "true"},
                        {"key": "lead_summary", "text": "Found in custom field list"},
                        {"label": "is_spam", "content": "false"},
                    ]
                }
            ]
        }

        enrich_call_custom_fields(call)

        self.assertIs(call["valid_lead"], True)
        self.assertEqual(call["lead_summary"], "Found in custom field list")
        self.assertIs(call["is_spam"], False)

    def test_unparseable_boolean_preserves_raw_value(self):
        call = {
            "custom_fields": {
                "valid_lead": "maybe",
                "is_spam": {"selected": "unknown"},
            }
        }

        enrich_call_custom_fields(call)

        self.assertIsNone(call["valid_lead"])
        self.assertEqual(call["valid_lead_raw"], "maybe")
        self.assertIsNone(call["is_spam"])
        self.assertEqual(call["is_spam_raw"], '{"selected": "unknown"}')

    def test_missing_fields_emit_nulls(self):
        call = {"id": 123}

        enrich_call_custom_fields(call)

        self.assertIsNone(call["valid_lead"])
        self.assertIsNone(call["valid_lead_raw"])
        self.assertIsNone(call["lead_summary"])
        self.assertIsNone(call["is_spam"])
        self.assertIsNone(call["is_spam_raw"])

    def test_null_custom_field_names_are_ignored(self):
        call = {
            "custom_fields": [
                {"name": None, "value": "ignored"},
                {"name": "valid_lead", "value": "true"},
            ]
        }

        enrich_call_custom_fields(call)

        self.assertIs(call["valid_lead"], True)
        self.assertEqual(call["valid_lead_raw"], "true")


if __name__ == "__main__":
    unittest.main()
