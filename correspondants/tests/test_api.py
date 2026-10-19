import json
from pathlib import Path
from unittest import mock

from django.test import TestCase, Client

from correspondants.models import (
    Capability,
    CapabilityExecution,
    CapabilityType,
    Correspondant,
)

FIXTURES = Path(__file__).parent / "fixtures"

PARSE_MAIL_CONFIG = {
    "match": {
        "sender": {"type": "contains", "value": "@freelancermap.example"}
    },
    "extractions": [
        {"key": "reference", "source": "subject", "pattern": r"PRJ-\d+-\d+"},
        {"key": "budget", "source": "body", "pattern": r"Budget: (.+)"},
    ],
}

SECOND_TEMPLATE_CONFIG = {
    "match": {"subject": {"type": "contains", "value": "Weekly newsletter"}},
    "extractions": [
        {"key": "tips", "source": "subject", "pattern": r"(\d+) tips"}
    ],
}

READ_PAGE_CONFIG = {
    "url_template": "/projects/{reference}",
    "selectors": [{"key": "title", "selector": "h1"}],
}


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class CapacitiesEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.correspondant = Correspondant.objects.create(
            name="freelancermap",
            base_url="https://www.freelancermap.example",
        )
        self.read_page_type = CapabilityType.objects.get(slug="read-page")
        self.parse_mail_type = CapabilityType.objects.get(slug="parse-mail")
        self.read_page = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.read_page_type,
            name="read-project-page",
            config=READ_PAGE_CONFIG,
        )
        self.parse_mail = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
            priority=1,
        )

    def get_json(self, url):
        response = self.client.get(url)
        return response, json.loads(response.content)

    def test_capacities_shape_and_ordering(self):
        response, data = self.get_json(
            "/api/correspondants/freelancermap/capacities"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["correspondant"], "freelancermap")
        self.assertEqual(len(data["capacities"]), 2)
        self.assertEqual(data["capacities"][0]["type"], "parse-mail")
        self.assertEqual(data["capacities"][1]["type"], "read-page")

    def test_description_falls_back_to_type_description(self):
        _, data = self.get_json(
            "/api/correspondants/freelancermap/capacities"
        )
        entry = data["capacities"][0]
        self.assertEqual(entry["description"], self.parse_mail_type.description)

    def test_instance_description_used_when_set(self):
        self.parse_mail.description = "Extract project references."
        self.parse_mail.save()
        _, data = self.get_json(
            "/api/correspondants/freelancermap/capacities"
        )
        self.assertEqual(
            data["capacities"][0]["description"], "Extract project references."
        )

    def test_verbose_mode_lists_resources(self):
        response, data = self.get_json(
            "/api/correspondants/freelancermap/capacities?verbose=1"
        )
        for entry in data["capacities"]:
            self.assertIn("resources", entry)
            self.assertIn("/api/correspondants/freelancermap/capacities/", entry["resources"]["self"])
            self.assertTrue(entry["resources"]["execute"].endswith("/execute"))

    def test_disabled_capability_excluded(self):
        self.parse_mail.enabled = False
        self.parse_mail.save()
        _, data = self.get_json(
            "/api/correspondants/freelancermap/capacities"
        )
        self.assertEqual(len(data["capacities"]), 1)
        self.assertEqual(data["capacities"][0]["name"], "read-project-page")

    def test_disabled_correspondant_returns_404(self):
        self.correspondant.enabled = False
        self.correspondant.save()
        response = self.client.get("/api/correspondants/freelancermap/capacities")
        self.assertEqual(response.status_code, 404)

    def test_unknown_correspondant_returns_404(self):
        response = self.client.get("/api/correspondants/nope/capacities")
        self.assertEqual(response.status_code, 404)

    def test_empty_capability_list(self):
        Correspondant.objects.create(name="empty", base_url="https://e.example")
        _, data = self.get_json("/api/correspondants/empty/capacities")
        self.assertEqual(data["capacities"], [])

    def test_capability_detail_masks_secrets(self):
        self.read_page.config = {
            "url_template": "/projects/{reference}",
            "selectors": [{"key": "title", "selector": "h1"}],
            "auth_token": "super-secret",
        }
        self.read_page.save()
        response = self.client.get(
            "/api/correspondants/freelancermap/capacities/read-project-page"
        )
        data = json.loads(response.content)
        self.assertEqual(data["config"]["auth_token"], "*****")
        self.assertEqual(data["input_schema"], self.read_page_type.input_schema)


class ExecuteEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.correspondant = Correspondant.objects.create(
            name="freelancermap",
            base_url="https://www.freelancermap.example",
        )
        self.parse_mail_type = CapabilityType.objects.get(slug="parse-mail")
        self.read_page_type = CapabilityType.objects.get(slug="read-page")
        self.main_template = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
            priority=0,
        )
        self.second_template = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.parse_mail_type,
            name="parse-newsletter-mail",
            config=SECOND_TEMPLATE_CONFIG,
            priority=10,
        )

    def execute(self, payload):
        return self.client.post(
            "/api/correspondants/freelancermap/capacities/parse-project-mail/execute",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_parse_mail_success_logged(self):
        response = self.execute({"raw_email": load_fixture("project_notification.eml")})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["matched"])
        self.assertEqual(data["matched_template"], "parse-project-mail")
        self.assertEqual(data["extractions"]["reference"], "PRJ-2026-0142")
        execution = CapabilityExecution.objects.get()
        self.assertEqual(execution.status, "success")
        self.assertEqual(execution.capability, self.main_template)

    def test_first_match_wins_by_priority(self):
        response = self.execute({"raw_email": load_fixture("newsletter.eml")})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["matched"])
        self.assertEqual(data["matched_template"], "parse-newsletter-mail")
        self.assertEqual(data["extractions"]["tips"], "10")

    def test_no_template_matches(self):
        raw = (
            "From: someone@unknown.example\r\n"
            "Subject: random\r\n\r\n"
            "Nothing to see here."
        )
        response = self.execute({"raw_email": raw})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data["matched"])
        self.assertEqual(data["extractions"], {})

    def test_invalid_input_rejected_400(self):
        response = self.execute({"unexpected": "payload"})
        self.assertEqual(response.status_code, 400)
        errors = json.loads(response.content)
        self.assertIn("errors", errors)

    def test_invalid_json_rejected_400(self):
        response = self.client.post(
            "/api/correspondants/freelancermap/capacities/parse-project-mail/execute",
            data="{not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unknown_capability_404(self):
        response = self.client.post(
            "/api/correspondants/freelancermap/capacities/nope/execute",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_unparseable_email_502_logged(self):
        response = self.execute({"raw_email": ""})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data["matched"])

    def test_read_page_with_mocked_browser(self):
        capability = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.read_page_type,
            name="read-project-page",
            config=READ_PAGE_CONFIG,
        )
        with mock.patch("correspondants.browser.fetch_page") as fetch_page, mock.patch(
            "correspondants.browser.extract_selector"
        ) as extract_selector:
            fetch_page.return_value = "<html><h1>Referentiel</h1></html>"
            extract_selector.return_value = ("Referentiel", True)
            response = self.client.post(
                "/api/correspondants/freelancermap/capacities/read-project-page/execute",
                data=json.dumps({"url_template_values": {"reference": "PRJ-1"}}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["url"], "https://www.freelancermap.example/projects/PRJ-1")
        self.assertEqual(data["extractions"][0]["key"], "title")

    def test_read_page_missing_template_values_502(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=self.read_page_type,
            name="read-project-page",
            config=READ_PAGE_CONFIG,
        )
        response = self.client.post(
            "/api/correspondants/freelancermap/capacities/read-project-page/execute",
            data=json.dumps({"url_template_values": {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 502)
        execution = CapabilityExecution.objects.get()
        self.assertEqual(execution.status, "error")
