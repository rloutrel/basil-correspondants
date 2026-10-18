from pathlib import Path

from django.test import TestCase

from correspondants.mail_parsing import (
    extract_value,
    match_field,
    matches_template,
    parse_raw_email,
    run_extractions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseRawEmailTests(TestCase):
    def test_project_notification(self):
        parsed = parse_raw_email(load_fixture("project_notification.eml"))
        self.assertEqual(parsed["sender"], "notifications@freelancermap.example")
        self.assertEqual(
            parsed["subject"], "New project PRJ-2026-0142: Référentiel E-commerce"
        )
        self.assertIn("PRJ-2026-0142", parsed["body"])
        self.assertEqual(
            parsed["headers"]["message-id"], "<abc123@freelancermap.example>"
        )

    def test_html_body_fallback(self):
        parsed = parse_raw_email(load_fixture("html_body.eml"))
        self.assertIn("Referentiel E-commerce", parsed["body"])
        self.assertIn("50000 EUR", parsed["body"])


class MatchFieldTests(TestCase):
    def test_exact_case_insensitive(self):
        self.assertTrue(
            match_field("Hello World", {"type": "exact", "value": "hello world"})
        )

    def test_exact_case_sensitive(self):
        self.assertFalse(
            match_field(
                "Hello World",
                {"type": "exact", "value": "hello world", "case_sensitive": True},
            )
        )

    def test_contains(self):
        self.assertTrue(
            match_field("a freelancermap update", {"type": "contains", "value": "freelancermap"})
        )

    def test_regex(self):
        self.assertTrue(
            match_field(
                "New project PRJ-2026-0142 online",
                {"type": "regex", "value": r"PRJ-\d+-\d+"},
            )
        )

    def test_no_match(self):
        self.assertFalse(
            match_field("nothing here", {"type": "contains", "value": "freelancermap"})
        )


class MatchesTemplateTests(TestCase):
    def test_and_logic_all_fields_match(self):
        parsed = parse_raw_email(load_fixture("project_notification.eml"))
        config = {
            "match": {
                "sender": {"type": "contains", "value": "freelancermap.example"},
                "subject": {"type": "regex", "value": "New project"},
            }
        }
        self.assertTrue(matches_template(parsed, config))

    def test_and_logic_one_field_fails(self):
        parsed = parse_raw_email(load_fixture("project_notification.eml"))
        config = {
            "match": {
                "sender": {"type": "contains", "value": "freelancermap.example"},
                "subject": {"type": "exact", "value": "invoice"},
            }
        }
        self.assertFalse(matches_template(parsed, config))


class ExtractionTests(TestCase):
    def setUp(self):
        self.parsed = parse_raw_email(load_fixture("project_notification.eml"))

    def test_single_capture_group_used(self):
        rule = {"key": "ref", "source": "subject", "pattern": r"(PRJ-\d+-\d+)"}
        self.assertEqual(extract_value(self.parsed, rule), "PRJ-2026-0142")

    def test_whole_match_when_no_group(self):
        rule = {"key": "ref", "source": "subject", "pattern": r"PRJ-\d+-\d+"}
        self.assertEqual(extract_value(self.parsed, rule), "PRJ-2026-0142")

    def test_two_groups_whole_match(self):
        rule = {"key": "ref", "source": "subject", "pattern": r"(PRJ)-(\d+)"}
        self.assertEqual(extract_value(self.parsed, rule), "PRJ-2026")

    def test_body_extraction_with_match_index(self):
        rule = {
            "key": "client",
            "source": "body",
            "pattern": r"Client: (.+)",
            "match_index": 0,
        }
        self.assertEqual(extract_value(self.parsed, rule), "ACME Corporation")

    def test_header_source_case_insensitive(self):
        rule = {
            "key": "mid",
            "source": "header",
            "header_name": "MESSAGE-ID",
            "pattern": r"([a-z0-9]+)@",
        }
        self.assertEqual(extract_value(self.parsed, rule), "abc123")

    def test_no_match_yields_empty_string(self):
        rule = {"key": "ref", "source": "subject", "pattern": r"INVOICE-\d+"}
        self.assertEqual(extract_value(self.parsed, rule), "")

    def test_strip_false(self):
        rule = {
            "key": "client",
            "source": "body",
            "pattern": r"Client:(.+)",
            "strip": False,
        }
        self.assertEqual(extract_value(self.parsed, rule), " ACME Corporation")

    def test_run_extractions_all_rules(self):
        config = {
            "extractions": [
                {"key": "reference", "source": "subject", "pattern": r"PRJ-\d+-\d+"},
                {"key": "budget", "source": "body", "pattern": r"Budget: ([\d ]+ EUR)"},
                {"key": "link", "source": "body", "pattern": r"(https://\S+)"},
            ]
        }
        result = run_extractions(self.parsed, config)
        self.assertEqual(result["reference"], "PRJ-2026-0142")
        self.assertEqual(result["budget"], "45 000 EUR")
        self.assertEqual(
            result["link"],
            "https://www.freelancermap.example/projects/PRJ-2026-0142",
        )
