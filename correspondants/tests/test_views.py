from django.test import TestCase

from correspondants.models import Capability, CapabilityType, Correspondant

PARSE_MAIL_CONFIG = {
    "match": {"sender": {"type": "contains", "value": "@freelancermap.example"}},
    "extractions": [
        {"key": "reference", "source": "subject", "pattern": r"PRJ-\d+-\d+"}
    ],
}


class IndexViewTests(TestCase):
    def test_index_renders_correspondants(self):
        correspondant = Correspondant.objects.create(
            name="freelancermap",
            display_name="Freelancermap",
            base_url="https://www.freelancermap.example",
        )
        Capability.objects.create(
            correspondant=correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Freelancermap")
        self.assertContains(response, "parse-project-mail")

    def test_index_empty_state(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No correspondant configured yet.")

    def test_login_redirect_target_resolves(self):
        from django.conf import settings
        from django.urls import resolve, reverse

        self.assertEqual(settings.LOGIN_REDIRECT_URL, "correspondants:correspondant_list")
        match = resolve(reverse(settings.LOGIN_REDIRECT_URL))
        self.assertEqual(match.view_name, "correspondants:correspondant_list")
