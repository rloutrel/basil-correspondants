"""Code-defined catalog of capability types.

The catalog is the single source of truth for the capability types shipped by
this service. It is a plain constant, reviewable in one place and testable
without the database. A data migration materializes it into CapabilityType
rows; the UI and API treat those rows as read-only.
"""

READ_PAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url_template_values": {
            "type": "object",
            "description": (
                "Values substituted into the configured URL template; keys "
                "must match the template placeholders."
            ),
            "additionalProperties": {"type": "string"},
        }
    },
    "required": [],
    "additionalProperties": False,
}

READ_PAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["url", "extractions"],
    "properties": {
        "url": {"type": "string", "format": "uri"},
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "value"],
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "found": {"type": "boolean"},
                },
            },
        },
    },
}

READ_PAGE_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["url_template", "selectors"],
    "properties": {
        "url_template": {
            "type": "string",
            "description": (
                "URL with {placeholder} tokens; rendered with values from the "
                "input. Relative templates are resolved against the "
                "correspondant's base_url."
            ),
        },
        "selectors": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["key", "selector"],
                "properties": {
                    "key": {"type": "string"},
                    "selector": {"type": "string"},
                    "selector_type": {"enum": ["css", "xpath"], "default": "css"},
                    "attribute": {
                        "type": "string",
                        "description": (
                            "Attribute to read instead of text content, "
                            "e.g. href."
                        ),
                    },
                    "multiple": {"type": "boolean", "default": False},
                },
            },
        },
        "wait_for_selector": {
            "type": "string",
            "description": "Optional selector to wait for before extraction.",
        },
        "navigation_timeout_ms": {
            "type": "integer",
            "minimum": 1000,
            "maximum": 60000,
        },
    },
}

PARSE_MAIL_INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Either a raw RFC 822 email (raw_email) or an already-parsed mail "
        "(sender, object, body). 'object' is the mail subject, named as by "
        "the upstream provider."
    ),
    "anyOf": [
        {
            "type": "object",
            "required": ["raw_email"],
            "properties": {
                "raw_email": {
                    "type": "string",
                    "description": "Full raw email (RFC 822 / MIME), as received.",
                }
            },
        },
        {
            "type": "object",
            "required": ["sender", "body"],
            "properties": {
                "sender": {"type": "string"},
                "object": {
                    "type": "string",
                    "description": "Mail subject (upstream field name).",
                },
                "subject": {
                    "type": "string",
                    "description": "Mail subject (standard name; alias of object).",
                },
                "body": {"type": "string"},
            },
            "additionalProperties": False,
        },
    ],
    "additionalProperties": False,
    "properties": {
        "raw_email": {"type": "string"},
        "sender": {"type": "string"},
        "object": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
}

PARSE_MAIL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["matched", "extractions"],
    "properties": {
        "matched": {"type": "boolean"},
        "matched_template": {
            "type": "string",
            "description": (
                "Name of the matching capability, absent when matched is "
                "false."
            ),
        },
        "extractions": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
}

FIELD_RULE_SCHEMA = {
    "type": "object",
    "required": ["type", "value"],
    "properties": {
        "type": {"enum": ["exact", "contains", "regex"]},
        "value": {"type": "string"},
        "case_sensitive": {"type": "boolean", "default": False},
    },
}

PARSE_MAIL_CONFIG_SCHEMA = {
    "type": "object",
    "required": ["match", "extractions"],
    "properties": {
        "match": {
            "type": "object",
            "description": (
                "AND-combined match rules on the parsed mail fields. All "
                "provided rules must match; at least one rule is required."
            ),
            "minProperties": 1,
            "properties": {
                "sender": FIELD_RULE_SCHEMA,
                "subject": FIELD_RULE_SCHEMA,
                "body": FIELD_RULE_SCHEMA,
            },
            "additionalProperties": False,
        },
        "extractions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "source"],
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Name of the extracted value in the output object."
                        ),
                    },
                    "source": {
                        "enum": [
                            "sender",
                            "subject",
                            "body",
                            "header",
                            "query_param",
                        ],
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Python regular expression (required unless source "
                            "is 'query_param'); if it contains exactly one "
                            "capture group, the group is used, otherwise the "
                            "whole match is used."
                        ),
                    },
                    "header_name": {
                        "type": "string",
                        "description": (
                            "Required when source is 'header', case-insensitive."
                        ),
                    },
                    "match_index": {
                        "type": "integer",
                        "minimum": 0,
                        "default": 0,
                        "description": (
                            "Index of the regex match to use when the pattern "
                            "matches several times."
                        ),
                    },
                    "strip": {"type": "boolean", "default": True},
                    "required": {
                        "type": "boolean",
                        "default": False,
                        "description": (
                            "If true, an empty extraction fails the execution "
                            "(content contract violation) instead of "
                            "returning an empty string."
                        ),
                    },
                    "from_key": {
                        "type": "string",
                        "description": (
                            "Required when source is 'query_param': key of a "
                            "previously extracted value (a URL); rules run in "
                            "array order, so the referenced rule must come "
                            "first."
                        ),
                    },
                    "param": {
                        "type": "string",
                        "description": (
                            "Required when source is 'query_param': query "
                            "parameter name to read from the URL."
                        ),
                    },
                },
            },
        },
    },
}

CAPABILITY_CATALOG = [
    {
        "slug": "read-page",
        "description": (
            "Access a page of the correspondant's website via a headless "
            "browser (Playwright) and extract information defined by "
            "CSS/XPath selectors."
        ),
        "input_schema": READ_PAGE_INPUT_SCHEMA,
        "output_schema": READ_PAGE_OUTPUT_SCHEMA,
        "config_schema": READ_PAGE_CONFIG_SCHEMA,
    },
    {
        "slug": "parse-mail",
        "description": (
            "Extract structured information from a raw email using a "
            "deterministic, template-based matcher (sender/subject/body "
            "rules plus extraction rules). No AI."
        ),
        "input_schema": PARSE_MAIL_INPUT_SCHEMA,
        "output_schema": PARSE_MAIL_OUTPUT_SCHEMA,
        "config_schema": PARSE_MAIL_CONFIG_SCHEMA,
    },
]

EXAMPLE_CONFIGS = {
    "read-page": {
        "url_template": "/projects/{reference}",
        "selectors": [
            {"key": "title", "selector": "h1", "selector_type": "css"},
            {"key": "link", "selector": "a.details", "attribute": "href"},
        ],
    },
    "parse-mail": {
        "match": {
            "sender": {"type": "contains", "value": "@notifications.example"},
            "subject": {"type": "regex", "value": "REF-\\d+"},
        },
        "extractions": [
            {"key": "reference", "source": "subject", "pattern": r"(REF-\d+)"},
            {"key": "client", "source": "body", "pattern": r"Client: (.+)"},
        ],
    },
}

FREELANCERMAP_POBOX_NOTIFICATION_CONFIG = {
    "match": {
        "sender": {
            "type": "exact",
            "value": "noreply@freelancermap.de",
            "case_sensitive": False,
        },
        "body": {
            "type": "contains",
            "value": "utm_campaign=pobox_benachrichtigung",
        },
    },
    "extractions": [
        {
            "key": "job_title",
            "source": "subject",
            "pattern": "^(.+)$",
            "required": True,
        },
        {
            "key": "portal_url",
            "source": "body",
            "pattern": (
                r"https://www\.freelancermap\.de/posteingang\.html"
                r"\?id=\d+&context=pobox&token=[A-Za-z0-9]+"
            ),
            "required": True,
        },
        {
            "key": "message_id",
            "source": "query_param",
            "from_key": "portal_url",
            "param": "id",
            "required": True,
        },
        {
            "key": "login_token",
            "source": "query_param",
            "from_key": "portal_url",
            "param": "token",
            "required": True,
        },
    ],
}

CATALOG_BY_SLUG = {entry["slug"]: entry for entry in CAPABILITY_CATALOG}
