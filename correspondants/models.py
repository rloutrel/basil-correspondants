from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import catalog
from .schemas import SchemaValidationError, validate

slug_validator = RegexValidator(
    regex=r"^[a-z0-9][a-z0-9-]*$",
    message=_("Only lowercase letters, digits and hyphens are allowed."),
)


class Correspondant(models.Model):
    name = models.CharField(
        _("Name"), max_length=64, unique=True, validators=[slug_validator]
    )
    display_name = models.CharField(_("Display name"), max_length=128, blank=True)
    base_url = models.URLField(_("Base URL"))
    enabled = models.BooleanField(_("Enabled"), default=True)
    notes = models.TextField(_("Notes"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("correspondant")
        verbose_name_plural = _("correspondants")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CapabilityType(models.Model):
    slug = models.CharField(
        _("Slug"), max_length=32, unique=True, choices=[(e["slug"], e["slug"]) for e in catalog.CAPABILITY_CATALOG]
    )
    description = models.TextField(_("Description"))
    input_schema = models.JSONField(_("Input schema"))
    output_schema = models.JSONField(_("Output schema"))
    config_schema = models.JSONField(_("Config schema"))

    class Meta:
        verbose_name = _("capability type")
        verbose_name_plural = _("capability types")
        ordering = ["slug"]

    def __str__(self):
        return self.slug


class Capability(models.Model):
    correspondant = models.ForeignKey(
        Correspondant, on_delete=models.CASCADE, related_name="capabilities"
    )
    capability_type = models.ForeignKey(
        CapabilityType, on_delete=models.PROTECT, related_name="capabilities"
    )
    name = models.CharField(
        _("Name"), max_length=64, validators=[slug_validator]
    )
    config = models.JSONField(_("Configuration"))
    enabled = models.BooleanField(_("Enabled"), default=True)
    priority = models.IntegerField(_("Priority"), default=0)
    description = models.TextField(_("Description"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("capability")
        verbose_name_plural = _("capabilities")
        ordering = ["capability_type__slug", "priority", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["correspondant", "name"],
                name="uniq_capability_per_correspondant",
            )
        ]
        indexes = [models.Index(fields=["correspondant", "capability_type"])]

    def __str__(self):
        return f"{self.correspondant.name}/{self.name}"

    def clean(self):
        super().clean()
        schema = self._effective_config_schema()
        try:
            validate(schema, self.config)
        except SchemaValidationError as exc:
            raise models.base.ValidationError({"config": exc.errors})
        if self.capability_type.slug == "parse-mail":
            self._validate_parse_mail_patterns()

    def _effective_config_schema(self):
        """The catalog constant is the source of truth; the DB copy may lag."""
        entry = catalog.CATALOG_BY_SLUG.get(self.capability_type.slug)
        if entry:
            return entry["config_schema"]
        return self.capability_type.config_schema

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def _validate_parse_mail_patterns(self):
        import re

        errors = []
        for rule in self.config.get("extractions", []):
            try:
                re.compile(rule.get("pattern", ""))
            except re.error:
                errors.append(
                    f"extraction {rule.get('key', '?')}: invalid regex "
                    f"{rule.get('pattern', '')!r}"
                )
        if self.config.get("match"):
            for field, rule in self.config["match"].items():
                if isinstance(rule, dict) and rule.get("type") == "regex":
                    try:
                        re.compile(rule.get("value", ""))
                    except re.error:
                        errors.append(f"match.{field}: invalid regex {rule['value']!r}")
        if errors:
            raise models.base.ValidationError({"config": errors})


class CapabilityExecution(models.Model):
    STATUS_CHOICES = [
        ("success", _("Success")),
        ("error", _("Error")),
    ]

    capability = models.ForeignKey(
        Capability, on_delete=models.CASCADE, related_name="executions"
    )
    input = models.JSONField(_("Input"))
    output = models.JSONField(_("Output"), null=True)
    error = models.TextField(_("Error"), blank=True)
    status = models.CharField(_("Status"), max_length=16, choices=STATUS_CHOICES)
    duration_ms = models.IntegerField(_("Duration (ms)"), null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("capability execution")
        verbose_name_plural = _("capability executions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.capability} — {self.status} — {self.created_at}"


class CapabilitySampleMail(models.Model):
    capability = models.ForeignKey(
        Capability, on_delete=models.CASCADE, related_name="sample_mails"
    )
    label = models.CharField(_("Label"), max_length=64, blank=True)
    content = models.TextField(_("Content"), blank=True)
    position = models.PositiveIntegerField(_("Position"), default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("sample mail")
        verbose_name_plural = _("sample mails")
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.capability} — {self.label or self.pk}"
