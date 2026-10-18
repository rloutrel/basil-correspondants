import json

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _

from .engines import CapabilityError, execute_capability
from .forms import CapabilityForm, CorrespondantForm
from .models import Capability, CapabilityType, Correspondant
from .schemas import SchemaValidationError

CLOSE_EVENT = "close-overlay"


def _capability_form_context(request, form, correspondant=None, capability=None):
    """Context shared by the capability form template (create and edit)."""
    from .catalog import EXAMPLE_CONFIGS

    example_configs = {
        str(capability_type.pk): json.dumps(
            EXAMPLE_CONFIGS[capability_type.slug], indent=2, ensure_ascii=False
        )
        for capability_type in CapabilityType.objects.all()
        if capability_type.slug in EXAMPLE_CONFIGS
    }
    return {
        "correspondant": correspondant or (capability.correspondant if capability else None),
        "form": form,
        "correspondant_name": (
            capability.correspondant.name if capability
            else (correspondant.name if correspondant else None)
        ),
        "capability_name": capability.name if capability else None,
        "example_configs": example_configs,
        "parse_mail_pk": str(
            CapabilityType.objects.get(slug="parse-mail").pk
        ),
    }


def correspondant_list(request):
    correspondants = Correspondant.objects.prefetch_related(
        "capabilities__capability_type"
    ).order_by("name")
    return render(
        request,
        "correspondants/index.html",
        {"correspondants": correspondants},
    )


def correspondant_create(request):
    if request.method == "POST":
        form = CorrespondantForm(request.POST)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
    else:
        form = CorrespondantForm()
    return render(
        request,
        "correspondants/partials/correspondant_form.html",
        {"form": form},
    )


def correspondant_edit(request, name):
    correspondant = get_object_or_404(Correspondant, name=name)
    if request.method == "POST":
        form = CorrespondantForm(request.POST, instance=correspondant)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
    else:
        form = CorrespondantForm(instance=correspondant)
    return render(
        request,
        "correspondants/partials/correspondant_form.html",
        {"form": form, "correspondant": correspondant},
    )


def correspondant_delete(request, name):
    correspondant = get_object_or_404(Correspondant, name=name)
    if request.method == "POST":
        correspondant.delete()
        return _list_refresh(request)
    return render(
        request,
        "correspondants/partials/confirm_delete.html",
        {"name": name},
    )


def capability_create(request, name):
    correspondant = get_object_or_404(Correspondant, name=name)
    capability = Capability(correspondant=correspondant)
    if request.method == "POST":
        form = CapabilityForm(request.POST, instance=capability)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
    else:
        form = CapabilityForm(instance=capability)
    return render(
        request,
        "correspondants/partials/capability_form.html",
        _capability_form_context(request, form, correspondant=correspondant),
    )


def capability_edit(request, name, capability_name):
    capability = get_object_or_404(
        Capability, correspondant__name=name, name=capability_name
    )
    if request.method == "POST":
        form = CapabilityForm(request.POST, instance=capability)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
    else:
        form = CapabilityForm(instance=capability)
    return render(
        request,
        "correspondants/partials/capability_form.html",
        _capability_form_context(request, form, capability=capability),
    )


def capability_delete(request, name, capability_name):
    capability = get_object_or_404(
        Capability, correspondant__name=name, name=capability_name
    )
    if request.method == "POST":
        capability.delete()
        return _list_refresh(request)
    return render(
        request,
        "correspondants/partials/confirm_delete.html",
        {"name": capability_name, "capability": True, "correspondant_name": name},
    )


def capability_preview(request, name, capability_name=None):
    """Live preview of a parse-mail capability while editing its config.

    Receives the draft config and one or two sample mails; runs the draft
    against each sample and returns the results as JSON. Deterministic: same
    inputs, same outputs; no external dependency. Used by the capability
    form (HTMX, triggered on config change) so the author sees the effect of
    the template immediately.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    config_raw = request.POST.get("config", "").strip()
    mails = [
        request.POST.get("sample_mail_1", "").strip(),
        request.POST.get("sample_mail_2", "").strip(),
    ]
    errors = []
    config = None
    try:
        config = json.loads(config_raw)
    except json.JSONDecodeError as exc:
        errors.append(_("Invalid JSON: %(error)s") % {"error": exc})
    if config is not None and capability_name:
        capability = get_object_or_404(
            Capability.objects.select_related("capability_type", "correspondant"),
            correspondant__name=name,
            name=capability_name,
        )
    elif config is not None:
        capability = Capability(
            correspondant=get_object_or_404(Correspondant, name=name),
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="draft",
        )
    else:
        capability = None
    if capability is not None and config is not None:
        capability.config = config
        try:
            capability.full_clean(
                exclude=["correspondant", "capability_type", "name", "enabled",
                         "priority", "description"]
            )
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field_errors in exc.message_dict.values():
                    if isinstance(field_errors, list):
                        errors.extend(str(e) for e in field_errors)
                    else:
                        errors.append(str(field_errors))
            else:
                errors.extend(str(e) for e in exc.error_list)
    results = []
    if not errors:
        from .engines import run_parse_mail

        draft = capability
        for index, mail_text in enumerate(mails, start=1):
            if not mail_text:
                continue
            payload, parse_error = _parse_mail_test_input(mail_text)
            if parse_error:
                results.append(
                    {"sample": index, "error": str(parse_error)}
                )
                continue
            try:
                output = run_parse_mail([draft], payload)
                results.append({
                    "sample": index,
                    "output": json.dumps(output, indent=2, ensure_ascii=False),
                })
            except CapabilityError as exc:
                results.append({"sample": index, "error": str(exc)})
    return render(
        request,
        "correspondants/partials/preview_results.html",
        {"errors": errors, "results": results},
    )


def _parse_mail_test_input(mail_text):
    """Accept a JSON mail ({sender, object, body}) or a raw RFC 822 email."""
    if not mail_text:
        return None, _("Paste a mail to test.")
    if mail_text.startswith("{"):
        try:
            return json.loads(mail_text), None
        except json.JSONDecodeError as exc:
            return None, _("Invalid JSON: %(error)s") % {"error": exc}
    return {"raw_email": mail_text}, None


def _list_refresh(request):
    correspondants = Correspondant.objects.prefetch_related(
        "capabilities__capability_type"
    ).order_by("name")
    response = render(
        request,
        "correspondants/partials/list.html",
        {"correspondants": correspondants},
    )
    response.headers["HX-Trigger"] = CLOSE_EVENT
    return response
