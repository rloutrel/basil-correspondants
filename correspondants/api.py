"""JSON API for capability discovery and execution.

Plain Django views on purpose: no DRF dependency, JSON built by hand so REST
and the future MCP adapter share the exact same document shape.
"""

import json

from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .engines import CapabilityError, execute_capability
from .models import Capability, Correspondant
from .schemas import SchemaValidationError

SECRET_MARKERS = ("password", "token", "secret", "cookie")


def _get_correspondant(name):
    try:
        return Correspondant.objects.get(name=name, enabled=True)
    except Correspondant.DoesNotExist:
        raise Http404("correspondant not found")


def _mask_config(config):
    if not isinstance(config, dict):
        return config
    masked = {}
    for key, value in config.items():
        if any(marker in key.lower() for marker in SECRET_MARKERS):
            masked[key] = "*****"
        else:
            masked[key] = value
    return masked


def _capability_entry(capability, verbose):
    description = capability.description or capability.capability_type.description
    entry = {
        "name": capability.name,
        "type": capability.capability_type.slug,
        "description": description,
        "enabled": capability.enabled,
    }
    if verbose:
        base = (
            f"/correspondants/{capability.correspondant.name}"
            f"/capacities/{capability.name}"
        )
        entry["resources"] = {"self": base, "execute": f"{base}/execute"}
    return entry


@require_GET
def capacities(request, name):
    correspondant = _get_correspondant(name)
    verbose = request.GET.get("verbose", "") in ("1", "true", "yes")
    capabilities = (
        correspondant.capabilities.filter(enabled=True)
        .select_related("capability_type", "correspondant")
        .order_by("capability_type__slug", "priority", "name")
    )
    return JsonResponse(
        {
            "correspondant": correspondant.name,
            "capacities": [_capability_entry(cap, verbose) for cap in capabilities],
        }
    )


@require_GET
def capability_detail(request, name, capability_name):
    correspondant = _get_correspondant(name)
    try:
        capability = correspondant.capabilities.select_related(
            "capability_type", "correspondant"
        ).get(name=capability_name)
    except Capability.DoesNotExist:
        raise Http404("capability not found")
    entry = _capability_entry(capability, verbose=False)
    entry.update(
        {
            "priority": capability.priority,
            "input_schema": capability.capability_type.input_schema,
            "output_schema": capability.capability_type.output_schema,
            "config": _mask_config(capability.config),
        }
    )
    return JsonResponse(entry)


def _read_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@require_POST
def capability_execute(request, name, capability_name):
    from .schemas import validate

    correspondant = _get_correspondant(name)
    try:
        capability = correspondant.capabilities.select_related(
            "capability_type", "correspondant"
        ).get(name=capability_name, enabled=True)
    except Capability.DoesNotExist:
        raise Http404("capability not found")

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "invalid JSON body"}, status=400)
    try:
        validate(capability.capability_type.input_schema, payload)
    except SchemaValidationError as exc:
        return JsonResponse({"detail": "input validation failed", "errors": exc.errors}, status=400)
    try:
        output = execute_capability(capability, payload)
    except SchemaValidationError as exc:
        return JsonResponse({"detail": "input validation failed", "errors": exc.errors}, status=400)
    except CapabilityError as exc:
        return JsonResponse({"detail": str(exc)}, status=502)
    return JsonResponse(output)
