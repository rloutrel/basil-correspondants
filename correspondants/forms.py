import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Capability, CapabilityType, Correspondant


class MaskedTextInput(forms.TextInput):
    """Text input that never renders its current value, so the stored
    password is never sent back to the browser and never offered to be
    saved as a credential (it is not a password-type input). Same approach
    as basil-mail."""

    def get_context(self, name, value, attrs):
        return super().get_context(name, "", attrs)


class CorrespondantForm(forms.ModelForm):
    password = forms.CharField(
        label=_("Password"),
        required=False,
        widget=MaskedTextInput(
            attrs={"autocomplete": "off", "placeholder": "(unchanged)"}
        ),
        help_text=_("Leave blank to keep the current password."),
    )

    class Meta:
        model = Correspondant
        fields = [
            "name", "display_name", "base_url", "login", "password",
            "enabled", "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def save(self, commit=True):
        correspondant = super().save(commit=False)
        if not self.cleaned_data.get("password"):
            if self.instance and self.instance.pk:
                correspondant.password = Correspondant.objects.get(
                    pk=self.instance.pk
                ).password
            else:
                correspondant.password = ""
        if commit:
            correspondant.save()
        return correspondant


class CapabilityForm(forms.ModelForm):
    config = forms.CharField(
        label="Configuration (JSON)",
        widget=forms.Textarea(attrs={"rows": 10}),
    )
    capability_type = forms.ModelChoiceField(
        queryset=CapabilityType.objects.all(),
        widget=forms.Select(attrs={"x-model": "type"}),
    )

    class Meta:
        model = Capability
        fields = ["name", "capability_type", "config", "enabled", "priority", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["config"].initial = json.dumps(
                self.instance.config, indent=2, ensure_ascii=False
            )

    def clean_config(self):
        raw = self.cleaned_data["config"]
        normalized = (
            raw.replace("\ufeff", "")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        try:
            return json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON: {exc}")
