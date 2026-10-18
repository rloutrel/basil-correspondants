"""Deterministic template-based raw email parsing (no AI).

Matching and extraction are pure functions of (raw_email, config): the same
inputs always produce the same output, fully unit-testable with fixture
emails — no network, no browser, no AI.
"""

import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr


class UnparseableEmailError(ValueError):
    pass


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
        if field not in parsed_mail:
            return False
        if not match_field(parsed_mail[field], rule):
            return False
    return True


def extract_value(parsed_mail, rule):
    """Apply one extraction rule; return the captured string ("" if no match)."""
    source = rule.get("source")
    if source == "header":
        value = parsed_mail["headers"].get(
            (rule.get("header_name") or "").lower(), ""
        )
    else:
        value = parsed_mail.get(source, "")
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
    return {
        rule["key"]: extract_value(parsed_mail, rule)
        for rule in config.get("extractions", [])
    }
