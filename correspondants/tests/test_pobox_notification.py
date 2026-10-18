import json
from pathlib import Path

from django.test import TestCase

from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG
from correspondants.mail_parsing import (
    matches_template,
    parse_mail_input,
    run_extractions,
)
from correspondants.models import Capability, CapabilityType, Correspondant
from correspondants.schemas import validate

FIXTURES = Path(__file__).parent / "fixtures" / "pobox"

EXPECTED = [
    {
        "job_title": (
            "(Senior) System Test Engineer (m/w/d) | ANÜ | Testautomatisierung "
            "Java / API Testing | Hybrid"
        ),
        "message_id": "4995147",
        "login_token": "sUXt4TuDSbRbCgv1eCDIRmTLZQfn7Ydwrj1AaiVn",
    },
    {
        "job_title": (
            "End-of-Line Testingenieur (m/w/d) – Leistungselektronik | LabVIEW "
            "/ NI TestStand / Python"
        ),
        "message_id": "4993600",
        "login_token": "8SZ4FnTOOk7ORX3UV74TfecOq3vSy3XkTJaueyN0",
    },
    {
        "job_title": "DevOps Engineer (m/w/d) | CI/CD | Kubernetes | Remote",
        "message_id": "4997231",
        "login_token": "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd",
    },
    {
        "job_title": "Softwarearchitekt (m/w/d) | Java | Microservices | München",
        "message_id": "4998456",
        "login_token": "Zz9Yy8Xx7Ww6Vv5Uu4Tt3Ss2Rr1Qq0Pp",
    },
]


def load_fixture(index):
    return json.loads((FIXTURES / f"pobox_{index}.json").read_text(encoding="utf-8"))


class PoboxNotificationTemplateTests(TestCase):
    """freelancermap-pobox-notification: concrete parse-mail template."""

    def test_config_validates_against_catalog_schema(self):
        config_schema = CapabilityType.objects.get(slug="parse-mail").config_schema
        validate(config_schema, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG)

    def test_matches_all_four_sample_mails(self):
        for index in range(1, 5):
            mail = load_fixture(index)
            parsed = parse_mail_input(mail)
            self.assertTrue(
                matches_template(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG),
                f"fixture {index} should match",
            )

    def test_never_matches_on_subject(self):
        mail = load_fixture(1)
        mail["object"] = "completely unrelated subject"
        parsed = parse_mail_input(mail)
        self.assertTrue(matches_template(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG))

    def test_does_not_match_other_sender(self):
        mail = load_fixture(1)
        mail["sender"] = "noreply@other-portal.de"
        parsed = parse_mail_input(mail)
        self.assertFalse(matches_template(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG))

    def test_does_not_match_without_campaign_marker(self):
        mail = load_fixture(1)
        mail["body"] = mail["body"].replace("pobox_benachrichtigung", "something_else")
        parsed = parse_mail_input(mail)
        self.assertFalse(matches_template(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG))

    def test_extracts_all_four_fields_for_each_sample(self):
        for index, expected in enumerate(EXPECTED, start=1):
            mail = load_fixture(index)
            parsed = parse_mail_input(mail)
            extractions = run_extractions(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG)
            self.assertEqual(extractions["job_title"], expected["job_title"])
            self.assertEqual(extractions["message_id"], expected["message_id"])
            self.assertEqual(extractions["login_token"], expected["login_token"])
            self.assertEqual(
                extractions["portal_url"],
                "https://www.freelancermap.de/posteingang.html"
                f"?id={expected['message_id']}&context=pobox"
                f"&token={expected['login_token']}",
            )

    def test_malformed_settings_url_never_extracted(self):
        for index in range(1, 5):
            mail = load_fixture(index)
            self.assertIn("https://https://www.freelancermap.de/dashboard/einstellungen", mail["body"])
            parsed = parse_mail_input(mail)
            extractions = run_extractions(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG)
            self.assertNotIn("einstellungen", extractions["portal_url"])
            self.assertNotIn("https://https://", extractions["portal_url"])
            self.assertTrue(extractions["portal_url"].startswith(
                "https://www.freelancermap.de/posteingang.html?id="
            ))

    def test_required_extraction_fails_on_empty_subject(self):
        mail = load_fixture(1)
        mail["object"] = ""
        parsed = parse_mail_input(mail)
        with self.assertRaises(Exception) as ctx:
            run_extractions(parsed, FREELANCERMAP_POBOX_NOTIFICATION_CONFIG)
        self.assertIn("job_title", str(ctx.exception))

    def test_template_runs_end_to_end_via_capability(self):
        from correspondants.engines import run_parse_mail

        correspondant = Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.de"
        )
        Capability.objects.create(
            correspondant=correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="freelancermap-pobox-notification",
            config=FREELANCERMAP_POBOX_NOTIFICATION_CONFIG,
        )
        capabilities = Capability.objects.filter(correspondant=correspondant)
        output = run_parse_mail(capabilities, load_fixture(1))
        self.assertTrue(output["matched"])
        self.assertEqual(
            output["matched_template"], "freelancermap-pobox-notification"
        )
        self.assertEqual(output["extractions"]["message_id"], "4995147")
