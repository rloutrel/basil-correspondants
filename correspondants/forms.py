import json

from django import forms
from django.core.exceptions import ValidationError

from .models import Capability, Correspondant


class CorrespondantForm(forms.ModelForm):
    class Meta:
        model = Correspondant
        fields = ["name", "display_name", "base_url", "enabled", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class CapabilityForm(forms.ModelForm):
    config = forms.CharField(
        label="Configuration (JSON)",
        widget=forms.Textarea(attrs={"rows": 10}),
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
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON: {exc}")
