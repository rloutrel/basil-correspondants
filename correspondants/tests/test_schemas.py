from django.test import TestCase

from correspondants import catalog
from correspondants.schemas import SchemaValidationError, validate


class SchemaValidatorTests(TestCase):
    def test_valid_parse_mail_config(self):
        config = {
            "match": {"sender": {"type": "contains", "value": "@freelancermap"}},
            "extractions": [
                {"key": "reference", "source": "subject", "pattern": "PRJ-\\d+-\\d+"}
            ],
        }
        validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)

    def test_missing_required_key(self):
        config = {"match": {"sender": {"type": "contains", "value": "x"}}}
        with self.assertRaises(SchemaValidationError) as ctx:
            validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)
        self.assertTrue(
            any("extractions" in e for e in ctx.exception.errors)
        )

    def test_empty_match_rejected(self):
        config = {"match": {}, "extractions": []}
        with self.assertRaises(SchemaValidationError):
            validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)

    def test_unknown_match_field_rejected(self):
        config = {
            "match": {"header_cc": {"type": "contains", "value": "x"}},
            "extractions": [],
        }
        with self.assertRaises(SchemaValidationError) as ctx:
            validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)
        self.assertTrue(any("additional property" in e for e in ctx.exception.errors))

    def test_bad_rule_type_rejected(self):
        config = {
            "match": {"sender": {"type": "fuzzy", "value": "x"}},
            "extractions": [],
        }
        with self.assertRaises(SchemaValidationError):
            validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)

    def test_bad_extraction_source_rejected(self):
        config = {
            "match": {"sender": {"type": "exact", "value": "x"}},
            "extractions": [
                {"key": "k", "source": "attachment", "pattern": "p"}
            ],
        }
        with self.assertRaises(SchemaValidationError):
            validate(catalog.PARSE_MAIL_CONFIG_SCHEMA, config)

    def test_valid_read_page_config(self):
        config = {
            "url_template": "/projects/{reference}",
            "selectors": [{"key": "title", "selector": "h1"}],
        }
        validate(catalog.READ_PAGE_CONFIG_SCHEMA, config)

    def test_read_page_selectors_min_items(self):
        config = {"url_template": "/x", "selectors": []}
        with self.assertRaises(SchemaValidationError):
            validate(catalog.READ_PAGE_CONFIG_SCHEMA, config)

    def test_read_page_input_schema(self):
        validate(catalog.READ_PAGE_INPUT_SCHEMA, {"url_template_values": {"a": "b"}})
        with self.assertRaises(SchemaValidationError):
            validate(catalog.READ_PAGE_INPUT_SCHEMA, {"unexpected": 1})

    def test_parse_mail_input_schema(self):
        validate(catalog.PARSE_MAIL_INPUT_SCHEMA, {"raw_email": "..."})
        with self.assertRaises(SchemaValidationError):
            validate(catalog.PARSE_MAIL_INPUT_SCHEMA, {})

    def test_catalog_entries_complete(self):
        slugs = {entry["slug"] for entry in catalog.CAPABILITY_CATALOG}
        self.assertEqual(slugs, {"read-page", "parse-mail"})
        for entry in catalog.CAPABILITY_CATALOG:
            for key in ("description", "input_schema", "output_schema", "config_schema"):
                self.assertIn(key, entry, entry["slug"])
