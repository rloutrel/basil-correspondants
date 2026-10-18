import json

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _

from .engines import CapabilityError, execute_capability
from .forms import CapabilityForm, CorrespondantForm
from .models import (
    Capability,
    CapabilitySampleMail,
    CapabilityType,
    Correspondant,
)
from .schemas import SchemaValidationError

CLOSE_EVENT = "close-overlay"


def _accordion_context():
    """Shared context for rendering capability accordions in the list."""
    from .catalog import EXAMPLE_CONFIGS

    capability_types = list(CapabilityType.objects.all())
    example_configs = {
        str(ct.pk): json.dumps(
            EXAMPLE_CONFIGS[ct.slug], indent=2, ensure_ascii=False
        )
        for ct in capability_types
        if ct.slug in EXAMPLE_CONFIGS
    }
    return {
        "capability_types": capability_types,
        "example_configs": example_configs,
    }


def correspondant_list(request):
    correspondants = Correspondant.objects.prefetch_related(
        "capabilities__capability_type"
    ).order_by("name")
    context = {"correspondants": correspondants}
    context.update(_accordion_context())
    return render(
        request,
        "correspondants/index.html",
        context,
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
        return _list_with_draft(
            request, name, draft_data=request.POST, errors=_form_error_list(form)
        )
    return _list_with_draft(request, name)


def capability_edit(request, name, capability_name):
    capability = get_object_or_404(
        Capability, correspondant__name=name, name=capability_name
    )
    if request.method == "POST":
        form = CapabilityForm(request.POST, instance=capability)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
        return _list_with_draft(
            request,
            name,
            capability=capability,
            draft_data=request.POST,
            errors=_form_error_list(form),
        )
    return _list_refresh(request)


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


def _draft_capability(request, name, capability_name, config_raw, errors):
    """Build an unsaved capability from the posted config for previewing."""
    config = None
    try:
        config = json.loads(_normalize_json_quotes(config_raw))
    except json.JSONDecodeError as exc:
        errors.append(_("Invalid JSON: %(error)s") % {"error": exc})
        return None
    if capability_name:
        capability = get_object_or_404(
            Capability.objects.select_related("capability_type", "correspondant"),
            correspondant__name=name,
            name=capability_name,
        )
    else:
        capability = Capability(
            correspondant=get_object_or_404(Correspondant, name=name),
            capability_type=CapabilityType.objects.get(slug="parse-mail"),
            name="draft",
        )
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
        return None
    return capability


def capability_preview(request, name, capability_name=None):
    """Run the draft config against one sample mail and return the result.

    The sample is either a saved sample mail (sample_id) or raw posted
    content (sample_content). Deterministic; no external dependency.
    """
    if request.method != "POST":
        return HttpResponse(status=405)
    errors = []
    capability = _draft_capability(
        request, name, capability_name,
        request.POST.get("config", ""), errors,
    )
    sample_label = ""
    sample_content = ""
    sample_id = request.POST.get("sample_id", "")
    if sample_id:
        sample = get_object_or_404(
            CapabilitySampleMail, pk=sample_id,
            capability__correspondant__name=name,
        )
        sample_label = sample.label
        sample_content = sample.content
    else:
        sample_content = request.POST.get("sample_content", "").strip()
        sample_label = request.POST.get("sample_label", "")
    result = None
    if capability is not None and sample_content:
        payload, parse_error = _parse_mail_test_input(sample_content)
        if parse_error:
            errors.append(str(parse_error))
        else:
            from .engines import run_parse_mail

            try:
                output = run_parse_mail([capability], payload)
                result = json.dumps(output, indent=2, ensure_ascii=False)
            except CapabilityError as exc:
                errors.append(str(exc))
    return render(
        request,
        "correspondants/partials/preview_results.html",
        {"errors": errors, "result": result, "label": sample_label},
    )


def sample_mail_add(request, name, capability_name):
    """Save a sample mail attached to a capability for future tests."""
    if request.method != "POST":
        return HttpResponse(status=405)
    capability = get_object_or_404(
        Capability, correspondant__name=name, name=capability_name
    )
    content = request.POST.get("sample_content", "").strip()
    if content:
        position = capability.sample_mails.count()
        CapabilitySampleMail.objects.create(
            capability=capability,
            label=request.POST.get("sample_label", "").strip(),
            content=content,
            position=position,
        )
    return _list_refresh(request)


def sample_mail_delete(request, name, capability_name, sample_id):
    if request.method != "POST":
        return HttpResponse(status=405)
    sample = get_object_or_404(
        CapabilitySampleMail, pk=sample_id,
        capability__correspondant__name=name,
        capability__name=capability_name,
    )
    sample.delete()
    return _list_refresh(request)


def _parse_mail_test_input(mail_text):
    """Accept a JSON mail ({sender, object, body}) or a raw RFC 822 email."""
    if not mail_text:
        return None, _("Paste a mail to test.")
    if mail_text.startswith("{"):
        normalized = _normalize_json_quotes(mail_text)
        try:
            return json.loads(normalized), None
        except json.JSONDecodeError as exc:
            hint = _(
                "Check that the quotes are straight double quotes and that "
                "the JSON is complete."
            )
            return None, _("Invalid JSON: %(error)s") % {"error": exc} + " " + hint
    return {"raw_email": mail_text}, None


def _normalize_json_quotes(text):
    """Replace typographic quotes pasted from word processors with the
    straight quotes JSON requires, and drop a UTF-8 BOM if present."""
    return (
        text.replace("\ufeff", "")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _form_error_list(form):
    errors = []
    for field, errs in form.errors.items():
        for err in errs:
            errors.append(f"{field}: {err}" if field != "__all__" else str(err))
    return errors


def _list_with_draft(request, name, capability=None, draft_data=None, errors=None):
    """Render the full list with one accordion open holding draft data."""
    correspondants = Correspondant.objects.prefetch_related(
        "capabilities__capability_type"
    ).order_by("name")
    context = {"correspondants": correspondants}
    context.update(_accordion_context())
    context["draft_correspondant_name"] = name
    context["draft_capability"] = capability
    context["draft_errors"] = errors or []
    if draft_data is not None:
        context["draft_values"] = {
            key: draft_data.get(key, "")
            for key in (
                "name", "capability_type", "priority", "enabled",
                "description", "config", "sample_mail_1", "sample_mail_2",
            )
        }
    return render(request, "correspondants/partials/list.html", context)


def _list_refresh(request):
    correspondants = Correspondant.objects.prefetch_related(
        "capabilities__capability_type"
    ).order_by("name")
    context = {"correspondants": correspondants}
    context.update(_accordion_context())
    response = render(
        request,
        "correspondants/partials/list.html",
        context,
    )
    response.headers["HX-Trigger"] = CLOSE_EVENT
    return response
