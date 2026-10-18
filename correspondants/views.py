import json

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


def capability_test(request, name, capability_name):
    """Interactive test of a parse-mail capability from the UI.

    Renders an input box (paste a mail), runs the capability on submit and
    shows the extraction result inline. Deterministic: same input, same
    output; no external dependency.
    """
    capability = get_object_or_404(
        Capability.objects.select_related("capability_type", "correspondant"),
        correspondant__name=name,
        name=capability_name,
        enabled=True,
    )
    result = None
    error = None
    mail_input = ""
    if request.method == "POST":
        mail_input = request.POST.get("mail_input", "").strip()
        payload, parse_error = _parse_mail_test_input(mail_input)
        if parse_error:
            error = parse_error
        else:
            try:
                output = execute_capability(capability, payload)
                result = json.dumps(output, indent=2, ensure_ascii=False)
            except CapabilityError as exc:
                error = str(exc)
            except SchemaValidationError:
                error = _("The mail does not match the expected input format.")
    return render(
        request,
        "correspondants/partials/capability_test.html",
        {
            "correspondant_name": name,
            "capability_name": capability_name,
            "mail_input": mail_input,
            "result": result,
            "error": error,
        },
    )


def _parse_mail_test_input(mail_input):
    """Accept a JSON mail ({sender, object, body}) or a raw RFC 822 email."""
    if not mail_input:
        return None, _("Paste a mail to test.")
    if mail_input.startswith("{"):
        try:
            return json.loads(mail_input), None
        except json.JSONDecodeError as exc:
            return None, _("Invalid JSON: %(error)s") % {"error": exc}
    return {"raw_email": mail_input}, None


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
