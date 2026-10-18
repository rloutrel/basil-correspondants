import json

from django.shortcuts import get_object_or_404, render

from .forms import CapabilityForm, CorrespondantForm
from .models import Capability, CapabilityType, Correspondant

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
