"""Deterministic template-based mail parsing (no AI).

Matching and extraction are pure functions of (mail, config): the same
inputs always produce the same output, fully unit-testable with fixture
emails — no network, no browser, no AI.

A mail is provided either as a raw RFC 822 email (raw_email) or already
parsed by the upstream provider (sender, object, body), where 'object' is
the provider's field name for the subject.
"""

import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from urllib.parse import parse_qs, urlsplit

FIELD_ALIASES = {"object": "subject"}


class UnparseableEmailError(ValueError):
    pass


class RequiredExtractionError(ValueError):
    """A rule flagged required extracted an empty value."""


def parse_raw_email(raw_email):
    """Parse a raw RFC 822 email into (sender, subject, body, headers)."""
    try:
        message = BytesParser(policy=policy.default).parsebytes(
            raw_email.encode("utf-8") if isinstance(raw_email, str) else raw_email
        )
    except Exception as exc:
        raise UnparseableEmailError(str(exc)) from exc
    sender = str(message.get("From", "") or "")
    subject = str(message.get("Subject", "") or "")
    body = _extract_body(message)
    headers = {k.lower(): str(v) for k, v in message.items()}
    return {
        "sender": parseaddr(sender)[1] or sender,
        "sender_full": sender,
        "subject": subject,
        "body": body,
        "headers": headers,
    }


def parse_mail_input(payload):
    """Normalize a capability input into the parsed-mail fields.

    Accepts either {"raw_email": ...} or {"sender": ..., "object": ...,
    "body": ...} (provider-parsed mail).
    """
    if "raw_email" in payload:
        return parse_raw_email(payload["raw_email"])
    subject = payload.get("object", "")
    if not subject:
        subject = payload.get("subject", "")
    return {
        "sender": payload.get("sender", ""),
        "sender_full": payload.get("sender", ""),
        "subject": subject,
        "body": payload.get("body", ""),
        "headers": {},
    }


def _extract_body(message):
    body_part = message.get_body(preferencelist=("plain",))
    if body_part is None:
        html_part = message.get_body(preferencelist=("html",))
        if html_part is None:
            return ""
        return html_part.get_content().replace("<br>", "\n").replace("<br/>", "\n")
    return body_part.get_content()


def _normalize(value, case_sensitive):
    value = re.sub(r"\s+", " ", value).strip()
    return value if case_sensitive else value.lower()


def match_field(field_value, rule):
    """Return True when one parsed mail field satisfies one match rule."""
    type_ = rule.get("type")
    value = rule.get("value", "")
    case_sensitive = rule.get("case_sensitive", False)
    target = _normalize(field_value, case_sensitive)
    expected = _normalize(value, case_sensitive)
    if type_ == "exact":
        return target == expected
    if type_ == "contains":
        return expected in target
    if type_ == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.search(value, field_value, flags) is not None
    raise ValueError(f"Unknown match type: {type_}")


def matches_template(parsed_mail, config):
    """Return True when every provided match rule matches (AND logic)."""
    match = config.get("match", {})
    for field, rule in match.items():
        if rule is None:
            continue
        normalized_field = FIELD_ALIASES.get(field, field)
        if normalized_field not in parsed_mail:
            return False
        if not match_field(parsed_mail[normalized_field], rule):
            return False
    return True


def extract_value(parsed_mail, rule, extractions=None):
    """Apply one extraction rule; return the captured string ("" if no match)."""
    extractions = extractions if extractions is not None else {}
    source = rule.get("source")
    if source == "query_param":
        url = extractions.get(rule.get("from_key", ""), "")
        try:
            captured = parse_qs(urlsplit(url).query).get(rule.get("param", ""), [""])[0]
        except ValueError:
            captured = ""
    else:
        normalized_source = FIELD_ALIASES.get(source, source)
        if source == "header":
            value = parsed_mail["headers"].get(
                (rule.get("header_name") or "").lower(), ""
            )
        else:
            value = parsed_mail.get(normalized_source, "")
        pattern = rule.get("pattern", "")
        matches = list(re.finditer(pattern, value))
        if not matches:
            return ""
        index = rule.get("match_index", 0)
        if index >= len(matches):
            return ""
        match = matches[index]
        if match.re.groups == 1:
            captured = match.group(1) or ""
        else:
            captured = match.group(0)
    if rule.get("strip", True):
        captured = captured.strip()
    return captured


def run_extractions(parsed_mail, config):
    """Run all extraction rules in order; return the output object."""
    extractions = {}
    for rule in config.get("extractions", []):
        value = extract_value(parsed_mail, rule, extractions)
        if rule.get("required") and not value:
            raise RequiredExtractionError(
                f"required extraction {rule.get('key', '?')} is empty"
            )
        extractions[rule["key"]] = value
    return extractions
