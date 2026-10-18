"""Capability runners: execute a capability instance against an input.

The parse-mail runner is fully deterministic. The read-page runner delegates
to a browser adapter which is always mocked in tests (never a real browser,
never network).
"""

import time

from django.db import transaction

from .mail_parsing import RequiredExtractionError
from .models import CapabilityExecution
from .schemas import SchemaValidationError, validate


class CapabilityError(Exception):
    """Infrastructure failure (network, timeout, unparseable input)."""


def run_parse_mail(capabilities, mail_input):
    """Try each enabled parse-mail capability in priority order.

    First matching template wins; returns the parse-mail output document.
    """
    from .mail_parsing import (
        UnparseableEmailError,
        matches_template,
        parse_mail_input,
        run_extractions,
    )

    try:
        parsed = parse_mail_input(mail_input)
    except UnparseableEmailError as exc:
        raise CapabilityError(str(exc)) from exc

    for capability in capabilities:
        if matches_template(parsed, capability.config):
            return {
                "matched": True,
                "matched_template": capability.name,
                "extractions": run_extractions(parsed, capability.config),
            }
    return {"matched": False, "extractions": {}}


def execute_capability(capability, payload):
    """Validate the input, run the capability, log the execution.

    Returns (output, execution). Raises SchemaValidationError for invalid
    input and CapabilityError for infrastructure failures.
    """
    started = time.monotonic()
    status = "success"
    output = None
    error = ""
    try:
        validate(capability.capability_type.input_schema, payload)
        if capability.capability_type.slug == "parse-mail":
            siblings = capability.__class__.objects.filter(
                correspondant_id=capability.correspondant_id,
                capability_type=capability.capability_type,
                enabled=True,
            ).order_by("priority", "name")
            output = run_parse_mail(siblings, payload)
        elif capability.capability_type.slug == "read-page":
            output = run_read_page(capability, payload)
        else:
            raise CapabilityError(
                f"Unknown capability type: {capability.capability_type.slug}"
            )
    except SchemaValidationError as exc:
        status = "error"
        error = "; ".join(exc.errors)
        raise
    except CapabilityError as exc:
        status = "error"
        error = str(exc)
        raise
    except RequiredExtractionError as exc:
        status = "error"
        error = str(exc)
        raise CapabilityError(str(exc)) from exc
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        with transaction.atomic():
            CapabilityExecution.objects.create(
                capability=capability,
                input=payload,
                output=output,
                error=error,
                status=status,
                duration_ms=duration_ms,
            )
    return output


def run_read_page(capability, payload):
    """Render the URL template and extract via the (mockable) browser adapter."""
    import re
    from urllib.parse import urljoin

    from .models import Correspondant

    config = capability.config
    template = config["url_template"]
    values = (payload or {}).get("url_template_values", {})

    placeholders = set(re.findall(r"\{([a-zA-Z0-9_]+)\}", template))
    missing = placeholders - set(values)
    if missing:
        raise CapabilityError(f"Missing URL template values: {sorted(missing)}")
    try:
        relative_url = template.format(**values)
    except (KeyError, IndexError) as exc:
        raise CapabilityError(f"Invalid URL template: {exc}") from exc
    url = urljoin(capability.correspondant.base_url, relative_url)
    if not url.startswith(("http://", "https://")):
        raise CapabilityError(f"Invalid rendered URL: {url}")

    from . import browser

    page_content = browser.fetch_page(
        url,
        wait_for_selector=config.get("wait_for_selector"),
        timeout_ms=config.get("navigation_timeout_ms"),
    )
    extractions = []
    for selector in config["selectors"]:
        try:
            value, found = browser.extract_selector(
                page_content,
                selector["selector"],
                selector_type=selector.get("selector_type", "css"),
                attribute=selector.get("attribute"),
            )
        except browser.BrowserError as exc:
            raise CapabilityError(str(exc)) from exc
        extractions.append(
            {"key": selector["key"], "value": value, "found": found}
        )
    return {"url": url, "extractions": extractions}
