from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .forms import CapabilityForm, CorrespondantForm
from .models import Capability, Correspondant

CLOSE_EVENT = "close-overlay"


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
        return _form_error(request, form)
    return render(
        request,
        "correspondants/partials/correspondant_form.html",
        {"form": CorrespondantForm()},
    )


def correspondant_edit(request, name):
    correspondant = get_object_or_404(Correspondant, name=name)
    if request.method == "POST":
        form = CorrespondantForm(request.POST, instance=correspondant)
        if form.is_valid():
            form.save()
            return _list_refresh(request)
        return _form_error(request, form)
    return render(
        request,
        "correspondants/partials/correspondant_form.html",
        {"correspondant": correspondant, "form": CorrespondantForm(instance=correspondant)},
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
    if request.method == "POST":
        form = CapabilityForm(request.POST)
        form.instance.correspondant = correspondant
        if form.is_valid():
            form.save()
            return _list_refresh(request)
        return _form_error(request, form)
    return render(
        request,
        "correspondants/partials/capability_form.html",
        {
            "correspondant": correspondant,
            "form": CapabilityForm(),
            "correspondant_name": name,
        },
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
        return _form_error(request, form)
    return render(
        request,
        "correspondants/partials/capability_form.html",
        {
            "correspondant": capability.correspondant,
            "form": CapabilityForm(instance=capability),
            "correspondant_name": name,
            "capability_name": capability_name,
        },
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


def _form_error(request, form):
    errors = "; ".join(
        f"{field}: {'; '.join(errs)}" for field, errs in form.errors.items()
    )
    return render(
        request,
        "correspondants/partials/form_error.html",
        {"errors": errors},
        status=400,
    )
