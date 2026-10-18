from django.db import migrations

from correspondants.catalog import CAPABILITY_CATALOG


def sync_catalog(apps, schema_editor):
    CapabilityType = apps.get_model("correspondants", "CapabilityType")
    for entry in CAPABILITY_CATALOG:
        CapabilityType.objects.update_or_create(
            slug=entry["slug"],
            defaults={
                "description": entry["description"],
                "input_schema": entry["input_schema"],
                "output_schema": entry["output_schema"],
                "config_schema": entry["config_schema"],
            },
        )


def unsync_catalog(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("correspondants", "0002_sync_catalog"),
    ]

    operations = [
        migrations.RunPython(sync_catalog, unsync_catalog),
    ]
