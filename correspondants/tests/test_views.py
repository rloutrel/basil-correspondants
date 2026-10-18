import json
from pathlib import Path
import os

from django.test import TestCase
from django.urls import reverse

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


class CorrespondantCrudTests(TestCase):
    def test_create_correspondant(self):
        response = self.client.post(
            reverse("correspondants:correspondant_create"),
            {
                "name": "freelancermap",
                "display_name": "Freelancermap",
                "base_url": "https://www.freelancermap.example",
                "enabled": "on",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Correspondant.objects.filter(name="freelancermap").exists()
        )
        self.assertContains(response, "freelancermap")
        self.assertEqual(response.headers["HX-Trigger"], "close-overlay")

    def test_create_correspondant_invalid_name(self):
        response = self.client.post(
            reverse("correspondants:correspondant_create"),
            {
                "name": "Invalid Name!",
                "base_url": "https://www.freelancermap.example",
                "enabled": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only lowercase letters")
        self.assertContains(response, "Invalid Name!")
        self.assertFalse(Correspondant.objects.exists())

    def test_edit_correspondant(self):
        Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.example"
        )
        response = self.client.post(
            reverse("correspondants:correspondant_edit", args=["freelancermap"]),
            {
                "name": "freelancermap",
                "display_name": "Freelancermap",
                "base_url": "https://www.freelancermap.example",
                "enabled": "on",
                "notes": "updated note",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Correspondant.objects.get(name="freelancermap").notes, "updated note"
        )

    def test_delete_correspondant(self):
        Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.example"
        )
        response = self.client.post(
            reverse("correspondants:correspondant_delete", args=["freelancermap"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Correspondant.objects.exists())

    def test_edit_form_renders(self):
        Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.example"
        )
        response = self.client.get(
            reverse("correspondants:correspondant_edit", args=["freelancermap"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "freelancermap")


class CapabilityCrudTests(TestCase):
    def setUp(self):
        self.correspondant = Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.example"
        )

    def capability_post_data(self, **overrides):
        data = {
            "name": "parse-project-mail",
            "capability_type": str(CapabilityType.objects.get(slug="parse-mail").pk),
            "config": json.dumps(PARSE_MAIL_CONFIG),
            "enabled": "on",
            "priority": "0",
            "description": "",
        }
        data.update(overrides)
        return data

    def test_create_capability(self):
        response = self.client.post(
            reverse("correspondants:capability_create", args=["freelancermap"]),
            self.capability_post_data(),
        )
        self.assertEqual(response.status_code, 200)
        capability = Capability.objects.get(name="parse-project-mail")
        self.assertEqual(capability.config, PARSE_MAIL_CONFIG)
        self.assertEqual(response.headers["HX-Trigger"], "close-overlay")

    def test_create_capability_invalid_json(self):
        response = self.client.post(
            reverse("correspondants:capability_create", args=["freelancermap"]),
            self.capability_post_data(config="{not json"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid JSON")
        self.assertFalse(Capability.objects.exists())

    def test_create_capability_schema_invalid_config_shows_field_errors(self):
        response = self.client.post(
            reverse("correspondants:capability_create", args=["freelancermap"]),
            self.capability_post_data(config=json.dumps({"match": {}})),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "missing required property")
        self.assertFalse(Capability.objects.exists())

    def test_create_capability_invalid_name_shows_field_error(self):
        response = self.client.post(
            reverse("correspondants:capability_create", args=["freelancermap"]),
            self.capability_post_data(name="Bad Name!"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only lowercase letters")
        self.assertContains(response, "Bad Name!")
        self.assertFalse(Capability.objects.exists())

    def test_create_form_renders_example(self):
        response = self.client.get(
            reverse("correspondants:capability_create", args=["freelancermap"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New capability")
        self.assertContains(response, "url_template")
        self.assertContains(response, "extractions")
        self.assertContains(response, 'name="config"')

    def test_edit_capability(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )
        response = self.client.post(
            reverse(
                "correspondants:capability_edit",
                args=["freelancermap", "parse-project-mail"],
            ),
            self.capability_post_data(priority="5"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Capability.objects.get(name="parse-project-mail").priority, 5
        )

    def test_list_renders_capability_accordion_with_config(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "accordion")
        self.assertContains(response, "parse-project-mail")
        self.assertContains(response, "PRJ-")
        self.assertContains(response, 'name="sample_mail_1"')

    def test_delete_capability(self):
        Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="parse-project-mail",
            config=PARSE_MAIL_CONFIG,
        )
        response = self.client.post(
            reverse(
                "correspondants:capability_delete",
                args=["freelancermap", "parse-project-mail"],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Capability.objects.exists())


class LanguageSwitchTests(TestCase):
    def test_index_contains_language_form(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="lang-form"')
        self.assertContains(response, 'id="lang-select"')
        for code, flag in (("de", "🇩🇪"), ("fr", "🇫🇷"), ("en", "🇬🇧")):
            self.assertContains(response, f'value="{code}"')

    def test_set_language_switches_to_french(self):
        from django.conf import settings

        response = self.client.post(
            "/i18n/setlang/", {"language": "fr", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/")
        self.assertContains(response, "Ajouter un correspondant")

    def test_base_uses_shared_ui_charte(self):
        response = self.client.get("/")
        self.assertContains(response, "/static/css/base.")
        self.assertContains(response, "basil-language")
        self.assertContains(response, "htmx.org")
        self.assertContains(response, "alpinejs")


class StaticFilesTests(TestCase):
    def test_base_css_served_with_css_mime_type(self):
        from django.conf import settings

        if not os.path.isdir(settings.STATIC_ROOT):
            self.skipTest("collectstatic has not been run")
        response = self.client.get("/static/css/base.css")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/css"))


class CapabilityPreviewTests(TestCase):
    def setUp(self):
        from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG

        self.correspondant = Correspondant.objects.create(
            name="freelancermap", base_url="https://www.freelancermap.de"
        )
        self.capability = Capability.objects.create(
            correspondant=self.correspondant,
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="freelancermap-pobox-notification",
            config=FREELANCERMAP_POBOX_NOTIFICATION_CONFIG,
        )
        self.url = reverse("correspondants:capability_preview", args=["freelancermap"])
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "pobox" / "pobox_1.json").read_text(
                encoding="utf-8"
            )
        )
        self.sample = json.dumps(fixture)

    def preview(self, config, sample_1=None, sample_2=None):
        return self.client.post(self.url, {
            "config": config,
            "sample_mail_1": sample_1 if sample_1 is not None else self.sample,
            "sample_mail_2": sample_2 or "",
        })

    def test_preview_with_valid_config_and_sample(self):
        from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG

        response = self.preview(json.dumps(FREELANCERMAP_POBOX_NOTIFICATION_CONFIG))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "matched_template")
        self.assertContains(response, "4995147")

    def test_preview_with_two_samples(self):
        from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG

        sample_2 = json.loads(
            (Path(__file__).parent / "fixtures" / "pobox" / "pobox_2.json").read_text(
                encoding="utf-8"
            )
        )
        response = self.preview(
            json.dumps(FREELANCERMAP_POBOX_NOTIFICATION_CONFIG),
            sample_2=json.dumps(sample_2),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "4995147")
        self.assertContains(response, "4993600")

    def test_preview_with_invalid_json_config(self):
        response = self.preview("{not json")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid JSON")

    def test_preview_with_schema_invalid_config(self):
        response = self.preview(json.dumps({"match": {}}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "missing required property")

    def test_preview_with_invalid_sample_shows_error(self):
        from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG

        response = self.preview(
            json.dumps(FREELANCERMAP_POBOX_NOTIFICATION_CONFIG),
            sample_1="{not json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid JSON")

    def test_preview_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_list_accordion_contains_live_test(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live test")
        self.assertContains(response, 'name="sample_mail_1"')
        self.assertContains(response, 'name="sample_mail_2"')

    def test_preview_accepts_typographic_quotes(self):
        from correspondants.catalog import FREELANCERMAP_POBOX_NOTIFICATION_CONFIG

        curly_sample = self.sample.replace('"', "\u201c")
        curly_config = json.dumps(
            FREELANCERMAP_POBOX_NOTIFICATION_CONFIG
        ).replace('"', "\u201c")
        response = self.preview(curly_config, sample_1=curly_sample)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Invalid JSON")
        self.assertContains(response, "matched_template")
        self.assertContains(response, "4995147")
