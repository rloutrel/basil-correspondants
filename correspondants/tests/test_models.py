from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase

from correspondants.models import (
    Capability,
    CapabilityExecution,
    CapabilityType,
    Correspondant,
)

PARSE_MAIL_CONFIG = {
    "match": {
        "sender": {"type": "contains", "value": "@freelancermap.example"}
    },
    "extractions": [
        {
            "key": "reference",
            "source": "subject",
            "pattern": r"PRJ-\d+-\d+",
        }
    ],
}


class CorrespondantModelTests(TestCase):
    def test_valid_correspondant(self):
        c = Correspondant.objects.create(
            name="freelancermap",
            base_url="https://www.freelancermap.example",
        )
        self.assertEqual(str(c), "freelancermap")

    def test_invalid_name_rejected(self):
        c = Correspondant(
            name="Freelancer Map!",
            base_url="https://www.freelancermap.example",
        )
        with self.assertRaises(ValidationError):
            c.save()

    def test_name_unique(self):
        Correspondant.objects.create(name="a-site", base_url="https://a.example")
        with self.assertRaises(ValidationError):
            Correspondant(name="a-site", base_url="https://b.example").save()


class CapabilityTypeCatalogTests(TestCase):
    def test_catalog_synced_by_data_migration(self):
        slugs = set(
            CapabilityType.objects.values_list("slug", flat=True)
        )
        self.assertEqual(slugs, {"read-page", "parse-mail"})

    def test_catalog_rows_match_catalog_constant(self):
        from correspondants import catalog

        for entry in catalog.CAPABILITY_CATALOG:
            row = CapabilityType.objects.get(slug=entry["slug"])
            self.assertEqual(row.description, entry["description"])
            self.assertEqual(row.input_schema, entry["input_schema"])
            self.assertEqual(row.output_schema, entry["output_schema"])
            self.assertEqual(row.config_schema, entry["config_schema"])

    def test_catalog_rows_protected_from_delete(self):
        row = CapabilityType.objects.get(slug="parse-mail")
        correspondant = Correspondant.objects.create(
            name="a-site", base_url="https://a.example"
        )
        Capability.objects.create(
            correspondant=correspondant,
            capability_type=row,
            name="cap",
            config=PARSE_MAIL_CONFIG,
        )
        with self.assertRaises(models.ProtectedError):
            row.delete()


class CapabilityModelTests(TestCase):
    def setUp(self):
        self.correspondant = Correspondant.objects.create(
            name="freelancermap",
            base_url="https://www.freelancermap.example",
        )
        self.parse_mail_type = CapabilityType.objects.get(slug="parse-mail")

    def test_valid_config_accepted(self):
        cap = Capability(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )
        cap.save()
        self.assertEqual(cap.priority, 0)

    def test_invalid_config_rejected(self):
        cap = Capability(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="bad-capability",
            config={"match": {}, "extractions": []},
        )
        with self.assertRaises(ValidationError):
            cap.save()

    def test_invalid_extraction_regex_rejected(self):
        config = {
            "match": {"sender": {"type": "contains", "value": "x"}},
            "extractions": [
                {"key": "k", "source": "subject", "pattern": "([unclosed"}
            ],
        }
        cap = Capability(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="bad-regex",
            config=config,
        )
        with self.assertRaises(ValidationError):
            cap.save()

    def test_invalid_match_regex_rejected(self):
        config = {
            "match": {"subject": {"type": "regex", "value": "[unclosed"}},
            "extractions": [],
        }
        cap = Capability(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="bad-match-regex",
            config=config,
        )
        with self.assertRaises(ValidationError):
            cap.save()

    def test_name_unique_per_correspondant(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="dup",
            config=PARSE_MAIL_CONFIG,
        )
        with self.assertRaises(ValidationError):
            Capability(
                correspondant=self.correspondant,
                capability_type=self.parse_mail_type,
                name="dup",
                config=PARSE_MAIL_CONFIG,
            ).save()

    def test_same_name_allowed_for_other_correspondant(self):
        other = Correspondant.objects.create(
            name="other-site", base_url="https://other.example"
        )
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="dup",
            config=PARSE_MAIL_CONFIG,
        )
        Capability.objects.create(
            correspondant=other,
            capability_type=self.parse_mail_type,
            name="dup",
            config=PARSE_MAIL_CONFIG,
        )
        self.assertEqual(Capability.objects.count(), 2)

    def test_cascade_from_correspondant(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="gone",
            config=PARSE_MAIL_CONFIG,
        )
        self.correspondant.delete()
        self.assertEqual(Capability.objects.count(), 0)


class CapabilityExecutionModelTests(TestCase):
    def setUp(self):
        self.capability = Capability.objects.create(
            correspondant=Correspondant.objects.create(
                name="freelancermap",
                base_url="https://www.freelancermap.example",
            ),
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )

    def test_execution_persisted_with_cascade(self):
        execution = CapabilityExecution.objects.create(
            capability=self.capability,
            input={"raw_email": "..."},
            output={"matched": True, "extractions": {}},
            status="success",
            duration_ms=12,
        )
        self.assertEqual(execution.status, "success")
        self.capability.delete()
        self.assertEqual(CapabilityExecution.objects.count(), 0)
