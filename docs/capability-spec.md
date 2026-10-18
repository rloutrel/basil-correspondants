# basil-correspondants — Capability System Specification

Status: **Specification only — no implementation yet.**

Basil (Basil — Assistant Synthétique à Intelligence Libre; English: Synthetic
Assistant with Free Intelligence) is a personal platform combining several
standalone components. This repository is the **correspondence component**:
it manages interactions with the outside world through *correspondants* —
external websites or services we exchange information with.

This document specifies the data model, capability contracts, API surface and
test strategy for the per-correspondant capability system. Everything is
configuration-driven and generic: **no business logic is hard-coded for any
specific site** (freelancermap is configuration data, nothing more). The
current phase is rules-based only; AI-powered extraction may be added later as
an additional capability type, never inside the existing ones.

---

## 1. Concepts

- **Correspondant**: an external site we interact with (e.g. `freelancermap`).
  A correspondant has capabilities.
- **CapabilityType**: a *kind* of capability, defined by code (the catalog).
  Each type declares a slug, a description, a JSON input schema, a JSON output
  schema and a required configuration schema. Two types exist initially:
  - `read-page` — access a page via Playwright and extract information.
  - `parse-mail` — extract structured information from a raw email, using
    deterministic, template-based matching and extraction.
- **Capability** (capability instance): the per-correspondant configuration of
  one capability type. A correspondant may have several instances of the same
  type (e.g. multiple `parse-mail` templates for different mail kinds).

Naming note: the API and MCP surfaces use the French word **"capacities"**
(plural), consistent with the resource URI
`basil://correspondants/{name}/capacities`. The Python model is named
`Capability` for clarity.

---

## 2. Data model (Django models)

All models live in a single app, `correspondants`. Field names below are the
exact Django field names to implement. Every model has the implicit
auto-generated `id` primary key unless stated otherwise.

### 2.1 `Correspondant`

A configured external site.

| Field | Type | Constraints |
|---|---|---|
| `name` | `CharField` | `max_length=64`, `unique=True`, slug pattern (`^[a-z0-9][a-z0-9-]*$`, validated), used in URLs and the MCP resource URI |
| `display_name` | `CharField` | `max_length=128`, `blank=True` (defaults to `name` in display contexts) |
| `base_url` | `URLField` | root URL of the site, used to resolve relative URL templates |
| `enabled` | `BooleanField` | `default=True`; disabled correspondants are excluded from the capacities listing and from MCP exposure |
| `notes` | `TextField` | `blank=True` |
| `created_at` | `DateTimeField` | `auto_now_add=True` |
| `updated_at` | `DateTimeField` | `auto_now=True` |

Relations: reverse FK `capabilities` from `Capability` (related name
`capabilities`, i.e. `correspondant.capabilities.all()`).

### 2.2 `CapabilityType` (catalog — code-defined, DB-materialized)

A code-defined entry per capability kind. Instances are created by a data
migration (the catalog) and are read-only from the UI/API; the catalog is the
source of truth for slug, description and schemas.

| Field | Type | Constraints |
|---|---|---|
| `slug` | `CharField` | `max_length=32`, `unique=True`, slug pattern, `choices` driven by a `Capabilities` registry constant in code (`read-page`, `parse-mail`) |
| `description` | `TextField` | human-readable, from the catalog constant |
| `input_schema` | `JSONField` | JSON Schema (Draft 2020-12) describing the input the capability accepts |
| `output_schema` | `JSONField` | JSON Schema describing the structured output the capability returns |
| `config_schema` | `JSONField` | JSON Schema describing the required per-instance configuration; used server-side to validate `Capability.config` |

The catalog is declared in code (`correspondants/catalog.py`) as a plain
constant (list of dataclass-like dicts) so it is testable without the DB and
reviewable in one place. A data migration syncs it into `CapabilityType` rows.

### 2.3 `Capability` (instance: per-correspondant configuration)

| Field | Type | Constraints |
|---|---|---|
| `correspondant` | `ForeignKey` | `to=Correspondant`, `on_delete=CASCADE`, `related_name="capabilities"` |
| `capability_type` | `ForeignKey` | `to=CapabilityType`, `on_delete=PROTECT` (catalog entries are never deleted while referenced) |
| `name` | `CharField` | `max_length=64`, instance name, unique together with `correspondant`; slug pattern recommended (used in tool/resource names) |
| `config` | `JSONField` | per-instance configuration, **validated at save time against `capability_type.config_schema`** |
| `enabled` | `BooleanField` | `default=True`; disabled instances are excluded from listing and execution |
| `priority` | `IntegerField` | `default=0`; ordering key for `parse-mail` template selection (see §5.3) |
| `description` | `TextField` | `blank=True`, optional per-instance description shown in verbose listings |
| `created_at` / `updated_at` | `DateTimeField` | `auto_now_add` / `auto_now` |

Constraints and indexes:

- `UniqueConstraint(fields=["correspondant", "name"],
  name="uniq_capability_per_correspondant")`.
- Index on `("correspondant", "capability_type")`.
- Model-level `clean()`/`save()` calls a JSON Schema validator
  (pure-Python, e.g. `jsonschema` — see Open questions) so invalid
  configuration cannot be persisted through any write path.

### 2.4 Execution log (minimal, phase 1)

A lean, append-only log of capability executions — useful for debugging and
for the daily-use page, without introducing a queue.

| Field | Type | Constraints |
|---|---|---|
| `capability` | `ForeignKey` | `to=Capability`, `on_delete=CASCADE`, `related_name="executions"` |
| `input` | `JSONField` | the validated input payload |
| `output` | `JSONField` | `null=True` — the structured output on success |
| `error` | `TextField` | `blank=True` — error message on failure |
| `status` | `CharField` | `choices=("success", "error")` |
| `duration_ms` | `IntegerField` | `null=True` |
| `created_at` | `DateTimeField` | `auto_now_add=True`, `db_index=True` |

No FK to any mail or page entity: inputs and outputs are self-contained JSON.
`input`/`output` never store secrets (credentials live only in the
correspondant/capability config, see §6).

---

## 3. Capability type contracts

Each contract is defined once in the catalog (`correspondants/catalog.py`) and
materialized in `CapabilityType`. Schemas are JSON Schema (Draft 2020-12).

### 3.1 `read-page`

- **slug**: `read-page`
- **description**: "Access a page of the correspondant's website via a
  headless browser (Playwright) and extract information defined by CSS/XPath
  selectors."

**Input schema**:

```json
{
  "type": "object",
  "properties": {
    "url_template_values": {
      "type": "object",
      "description": "Values substituted into the configured URL template; keys must match the template placeholders.",
      "additionalProperties": { "type": "string" }
    }
  },
  "required": [],
  "additionalProperties": false
}
```

**Output schema**:

```json
{
  "type": "object",
  "required": ["url", "extractions"],
  "properties": {
    "url": { "type": "string", "format": "uri" },
    "extractions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["key", "value"],
        "properties": {
          "key": { "type": "string" },
          "value": { "type": "string" },
          "found": { "type": "boolean" }
        }
      }
    }
  }
}
```

**Required config schema** (stored in `Capability.config`):

```json
{
  "type": "object",
  "required": ["url_template", "selectors"],
  "properties": {
    "url_template": {
      "type": "string",
      "description": "URL with {placeholder} tokens; rendered with values from the input. Relative templates are resolved against the correspondant's base_url."
    },
    "selectors": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["key", "selector"],
        "properties": {
          "key": { "type": "string" },
          "selector": { "type": "string" },
          "selector_type": { "enum": ["css", "xpath"], "default": "css" },
          "attribute": { "type": "string", "description": "Attribute to read instead of text content, e.g. href." },
          "multiple": { "type": "boolean", "default": false }
        }
      }
    },
    "wait_for_selector": { "type": "string", "description": "Optional selector to wait for before extraction." },
    "navigation_timeout_ms": { "type": "integer", "minimum": 1000, "maximum": 60000 }
  }
}
```

Semantics: the URL template is rendered with the input values (unknown
placeholder → validation error before any network call); Playwright loads the
page; each selector entry produces one `extractions` item. Deterministic,
fail-soft: a selector matching nothing yields `found: false` and empty value,
never an execution error.

### 3.2 `parse-mail`

- **slug**: `parse-mail`
- **description**: "Extract structured information from a raw email using a
  deterministic, template-based matcher (sender/subject/body rules plus
  extraction rules). No AI."

**Input schema**:

```json
{
  "type": "object",
  "description": "Either a raw RFC 822 email (raw_email) or an already-parsed mail (sender, object, body). 'object' is the mail subject, named as by the upstream provider.",
  "anyOf": [
    { "type": "object", "required": ["raw_email"],
      "properties": { "raw_email": { "type": "string", "description": "Full raw email (RFC 822 / MIME), as received." } } },
    { "type": "object", "required": ["sender", "object", "body"],
      "properties": {
        "sender": { "type": "string" },
        "object": { "type": "string", "description": "Mail subject (upstream field name)." },
        "body": { "type": "string" }
      } }
  ],
  "additionalProperties": false
}
```

Extraction sources: `sender`, `subject` (alias `object`, the upstream
field name), `body`, `header`, and `query_param` — reading a query
parameter from a previously extracted URL (`from_key` + `param`; rules run
in array order, so the referenced rule must come first). Rules may set
`required: true`: an empty extraction then fails the execution (content
contract violation) instead of returning an empty string.

**Output schema**:

```json
{
  "type": "object",
  "required": ["matched", "extractions"],
  "properties": {
    "matched": { "type": "boolean" },
    "matched_template": { "type": "string", "description": "Name of the matching template, absent when matched is false." },
    "extractions": {
      "type": "object",
      "additionalProperties": { "type": "string" }
    }
  }
}
```

On `matched: false`, `extractions` is `{}` and the email is reported as
"unrecognized" (the caller — e.g. basil-mail — decides what to do with it;
nothing is ever auto-sent, see §6).

**Required config schema** (stored in `Capability.config`) — one template per
`parse-mail` capability instance (multiple mail kinds = multiple instances,
ordered by `priority`):

```json
{
  "type": "object",
  "required": ["match", "extractions"],
  "properties": {
    "match": {
      "type": "object",
      "description": "AND-combined match rules on the parsed mail fields. All provided rules must match; at least one rule is required.",
      "minProperties": 1,
      "properties": {
        "sender": { "$ref": "#/$defs/field_rule" },
        "subject": { "$ref": "#/$defs/field_rule" },
        "body": { "$ref": "#/$defs/field_rule" }
      },
      "additionalProperties": false
    },
    "extractions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["key", "source", "pattern"],
        "properties": {
          "key": { "type": "string", "description": "Name of the extracted value in the output object." },
          "source": { "enum": ["sender", "subject", "body", "header"] },
          "pattern": { "type": "string", "description": "Python regular expression; if it contains exactly one capture group, the group is used, otherwise the whole match is used." },
          "header_name": { "type": "string", "description": "Required when source is 'header', case-insensitive." },
          "match_index": { "type": "integer", "minimum": 0, "default": 0, "description": "Index of the regex match to use when the pattern matches several times." },
          "strip": { "type": "boolean", "default": true }
        }
      }
    }
  },
  "$defs": {
    "field_rule": {
      "type": "object",
      "required": ["type", "value"],
      "properties": {
        "type": { "enum": ["exact", "contains", "regex"] },
        "value": { "type": "string" },
        "case_sensitive": { "type": "boolean", "default": false }
      }
    }
  }
}
```



---

## 4. API contract — capabilities discovery

Endpoint: `GET /api/correspondants/{name}/capacities`

Note the URL prefix is `/api/correspondants/` — everything API lives behind the `[base]/api/` prefix (the plural of the service domain follows);
`{name}` is the correspondant `name` slug. The user-visible French label is
"Capacités" via i18n; URLs stay English/slug-based.

### 4.1 Default (non-verbose) response

`Status: 200 OK`, content type `application/json` (the endpoint is
API-oriented; the UI pages consume it via HTMX or server-side templates).

```json
{
  "correspondant": "freelancermap",
  "capacities": [
    {
      "name": "read-project-page",
      "type": "read-page",
      "description": "Read a project page and extract the title, budget and publication date.",
      "enabled": true
    },
    {
      "name": "parse-project-mail",
      "type": "parse-mail",
      "description": "Extract project reference, client name and link from a project notification mail.",
      "enabled": true
    }
  ]
}
```

Rules:

- Only `enabled=True` capabilities of an `enabled=True` correspondant are
  listed, ordered by `capability_type.slug`, then `priority`, then `name`.
- Unknown correspondant name → `404` with `{"detail": "correspondant not found"}`.
- Disabled correspondant → `404` (indistinguishable from unknown, to avoid
  leaking disabled configuration).
- `description` is the per-instance description if set, otherwise the type
  description from the catalog.

### 4.2 Verbose mode

`GET /api/correspondants/{name}/capacities?verbose=1` (also `verbose=true`).

Each entry additionally carries its REST resources:

```json
{
  "correspondant": "freelancermap",
  "capacities": [
    {
      "name": "read-project-page",
      "type": "read-page",
      "description": "…",
      "enabled": true,
      "resources": {
        "self": "/api/correspondants/freelancermap/capacities/read-project-page",
        "execute": "/api/correspondants/freelancermap/capacities/read-project-page/execute"
      }
    }
  ]
}
```

- `self`: capability detail (GET) — returns the entry plus its type's input,
  output and config schemas (config values may include secrets; the detail
  endpoint masks secret-looking config keys — see §6).
- `execute`: POST endpoint accepting a payload validated against the type's
  input schema; returns the output validated against the type's output schema
  (`202`-style async execution is out of scope for phase 1: synchronous
  response, execution logged in `CapabilityExecution`).

### 4.3 Consistency with MCP exposure

The same listing is exposed through the future MCP server as:

- **Resource**: `basil://correspondants/{name}/capacities` — the JSON document
  of §4.1 (verbose listing is the natural expansion the client requests).
- **Tools**: one tool per (enabled) capability instance,
  `correspondant_{name}_{capability_name}` (e.g.
  `correspondant_freelancermap_parse_project_mail`), with the type's input
  schema as the tool input schema and the output schema as the tool output
  schema. Tool descriptions reuse the capability description.

Phase 1 ships the REST endpoint only; the MCP adapter consumes the same
serializer so REST and MCP cannot drift. MCP servers (as *clients* of external
tools, e.g. Playwright MCP) remain mocked in tests and are themselves a later
delivery.

---

## 5. Extraction rules design (`parse-mail`)

### 5.1 Principles

- **Deterministic**: same `(raw_email, template_config)` → same output, always.
- **No AI**: `re` module only, plus Python `email` parsing (stdlib) for
  header/body extraction. HTML bodies are converted to text first
  (html→text fallback), reusing the same approach as basil-mail.
- **Declarative**: everything a template does is data in `config`, validated
  against the config schema — nothing site-specific in code.

### 5.2 Matching

- The raw email is parsed once with the stdlib `email` package:
  `sender` (From header), `subject` (Subject header, decoded per RFC 2047),
  `body` (first text/plain part; html→text fallback for text/html).
- `match` rules are AND-combined across the fields present in the rule object.
- Field rule types: `exact` (full equality), `contains` (substring), `regex`
  (`re.search`, pattern validated at save time). `case_sensitive` defaults to
  false; matching operates on the decoded, whitespace-normalized values.
- A template matches only if **all** its rules match; a config with no rule is
  rejected by the schema (`minProperties: 1`).

### 5.3 Priority and template selection

Several `parse-mail` instances may exist per correspondant (one per mail
kind). For a given raw email:

1. Candidates are all enabled `parse-mail` capabilities of the correspondant,
   ordered by `priority` ascending, then `name` (stable, explicit tie-break).
2. The **first matching template wins**; extraction runs against it and stops
   (no overlap, no merge — deterministic and explainable).
3. If no template matches, the result is `{"matched": false, "extractions": {}}`.

`priority` is therefore a first-class, user-controlled ordering field on
`Capability`, not a property of the config JSON — it stays visible in the UI
list and manipulable independently of the template body.

### 5.4 Extraction

- Rules run in array order against the parsed mail; each produces
  `output.extractions[key]`.
- `pattern` is a Python regex: with exactly one capture group, the group is
  captured; with zero or 2+ groups, the whole match is captured. Regexes are
  compiled and validated at save time (invalid → validation error).
- `match_index` selects which occurrence to use when the pattern matches
  several times (deterministic, no "best match" heuristics).
- A non-matching extraction rule yields the key with an empty string (and the
  output schema allows `additionalProperties: string`), so downstream
  consumers can distinguish "absent" from "template did not match".
- `strip` (default true) trims whitespace around the captured value.

### 5.5 Concrete template: `freelancermap-pobox-notification`

A real parse-mail template, shipped as reference configuration (it is pure
configuration data — nothing freelancermap-specific lives in code). It matches
freelancermap postfach-notification mails (JSON-parsed by the upstream
provider as `{sender, object, body}`; `object` is the provider's field name
for the subject) and extracts the data needed to reach the message on the
portal.

**Match rules** (all must pass; the subject is never matched — it is variable
and sometimes generic):

- `sender`: exact `noreply@freelancermap.de`
- `body`: contains `utm_campaign=pobox_benachrichtigung`

**Extraction rules** (declarative, deterministic):

- `job_title` (required): the subject, verbatim.
- `portal_url` (required): first body URL matching the allowlist regex
  `https://www\.freelancermap\.de/posteingang\.html\?id=\d+&context=pobox&token=[A-Za-z0-9]+`.
  This is an allowlist pattern, not "extract all links": the body also
  contains a malformed settings URL (`https://https://www.freelancermap.de/dashboard/einstellungen`)
  which must never be extracted.
- `message_id` (required): query param `id` of `portal_url`.
- `login_token` (required): query param `token` of `portal_url` (24-hour,
  single-use login token; never to be forwarded — the notification mail says
  so itself).

**Output contract** (per-instance contract, expressed by the config):

```json
{
  "job_title": "(Senior) System Test Engineer (m/w/d) | ANÜ | Testautomatisierung Java / API Testing | Hybrid",
  "portal_url": "https://www.freelancermap.de/posteingang.html?id=4995147&context=pobox&token=sUXt4TuDSbRbCgv1eCDIRmTLZQfn7Ydwrj1AaiVn",
  "message_id": "4995147",
  "login_token": "sUXt4TuDSbRbCgv1eCDIRmTLZQfn7Ydwrj1AaiVn"
}
```

The exact configuration lives in `correspondants/catalog.py`
(`FREELANCERMAP_POBOX_NOTIFICATION_CONFIG`); four sample mails are checked
in as test fixtures (`correspondants/tests/fixtures/pobox/pobox_{1..4}.json`).

**Design note — links between capabilities**: these notification mails do NOT
contain the job description. The description lives behind `portal_url` on
the site itself, so consuming it is the `read-page` capability's job, not
parse-mail's. The template contract therefore expresses that parse-mail
outputs are sometimes *inputs for other capabilities*: a `read-page`
capability instance can declare `portal_url` (or a URL template
parameterized by `message_id`) as its input, chaining the two capabilities.
In the current REST API this chaining is done by the caller (orchestration,
e.g. basil-concierge); the capacities listing exposes both capabilities so
any consumer can discover the chain. A future evolution may declare the
chaining itself in configuration (capability input referencing another
capability's output key) — out of scope for this phase.

### 5.6 Testability consequences

- Matching + extraction is a single pure function, unit-testable against
  fixture `.eml` files (checked into the repo, anonymized).
- Schema validation of configs is unit-testable against the catalog schemas.
- No mocks needed for the extraction core itself; mocks only apply to
  Playwright (read-page) and the future MCP layer.

---

## 6. Security and constraints

- **No automatic sending, ever**: this service produces extracted data and
  structured outputs; any generated message to a third party requires
  mandatory human validation (enforced upstream in basil-scribe/concierge, but
  the principle holds: basil-correspondants never sends anything).
- **Secrets in config**: `read-page` templates may need authentication later
  (cookies, tokens). Config values matching a secret-looking key
  (`password`, `token`, `secret`, `cookie`) are masked in any API/UI output.
  Credential storage strategy (Django-encrypted JSON field vs. delegated to
  basil-chambellan) is an open question (§8).
- **Validation everywhere**: input validated against the type input schema
  before execution; config validated against the config schema at save time;
  output validated against the output schema before returning (defense in
  depth, and the execution log always contains schema-valid payloads).
- **Fail soft**: read-page selector misses and parse-mail non-matches are
  normal results, not errors; only infrastructure failures (network,
  navigation timeout, unparseable email) produce `status="error"` executions.

---

## 7. Test strategy outline

Testing is maintained throughout development (per project convention), with
Django's built-in framework, PostgreSQL in CI (no SQLite anywhere), and every
external dependency mocked.

### 7.1 Model layer

- `Correspondant`: name slug validation (invalid names rejected), uniqueness,
  `base_url` required, cascade behavior to capabilities.
- `CapabilityType` catalog sync: data migration creates exactly the catalog
  rows; slugs unique; schema fields are valid JSON Schema documents.
- `Capability`:
  - unique `(correspondant, name)`;
  - `config` validated against `config_schema` at save (valid config passes;
    each schema-invalid config variant — missing key, bad regex, wrong rule
    type — fails with a readable error);
  - `on_delete=PROTECT` on `capability_type` (deleting a catalog row raises).
- `CapabilityExecution`: FK cascade from capability, status choices enforced.

### 7.2 Capabilities endpoint

- Factory fixtures: correspondant `freelancermap` with one `read-page` and two
  `parse-mail` capabilities (different priorities) — proving genericity: the
  fixtures are configuration data, no hard-coded site logic anywhere.
- `GET /api/correspondants/{name}/capacities`:
  - 200 with expected shape, ordering (type, priority, name);
  - disabled capabilities excluded; disabled correspondant → 404; unknown → 404;
  - `verbose=1` adds `resources` with correct paths;
  - `description` fallback to the type description when unset;
  - empty list for a correspondant with no capability.
- `execute` endpoint (when delivered): input-schema validation errors → 400
  with schema-located error details; Playwright mocked at the adapter
  boundary (a fake page object returning canned DOM/selector results — never
  a real browser, never network); output conforms to the output schema;
  execution row logged with status and duration.

### 7.3 parse-mail engine

- Pure-function tests over fixture `.eml` files: exact/contains/regex match
  per field; AND-combination; case sensitivity; priority ordering and
  first-match-wins; no-match → `matched: false`; capture-group semantics
  (0/1/2 groups); `match_index`; `strip`; `header` source (case-insensitive
  header name); RFC 2047-encoded subjects; html→text body fallback.

### 7.4 What is always mocked (never a real server)

Playwright/browser (fake adapter), IMAP/mail origins (fixtures only), MCP
client/servers, any outbound HTTP. CI runs the full suite on every change.

---

## 8. Open questions

1. **JSON Schema validation library**: `jsonschema` (MIT-ish? — to verify:
   currently LGPL-derived history, needs a license check against the
   permissive-only rule) vs. a small hand-rolled validator limited to the
   subset of keywords used by the two catalogs. Lean approach suggests
   hand-rolled subset, but `jsonschema` is the standard choice — decide before
   implementation.
2. **Secret storage**: encrypt secret config values at rest (which library?)
   or delegate credential management to basil-chambellan (its stated purpose)
   and keep only a reference here?
3. **Execute endpoint timing**: synchronous with an HTTP timeout vs.
   job-style `202 Accepted` + polling resource, especially for `read-page`
   (Playwright runs can take seconds). Phase 1 assumes synchronous — confirm.
4. **MCP server scope**: is the MCP adapter part of basil-correspondants
   itself or of a shared gateway (basil-concierge)? The resource URI scheme
   (`basil://…`) is agreed, the hosting is not.
5. **Capability config versioning**: when a config schema evolves, existing
   `Capability.config` rows may become invalid. Do we need a lightweight
   schema-version field on `CapabilityType` plus a re-validation migration?
6. **Rate limiting / politeness**: should `read-page` carry per-correspondant
   fetch-rate limits (robots/politeness) in the correspondant config, or is
   that an orchestration concern for basil-concierge?
7. **Multi-value extractions on read-page**: `multiple: true` selectors return
   several values — should the output schema allow arrays per key now, or
   stay strings-only until a real use case appears?
8. **UI mapping**: confirm the two-page plan for this service (daily-use page:
  correspondant list + capacities + execution log; configuration page:
  correspondant/capability editing) fits the max-2-pages rule, or whether the
  execution log should be folded into the daily page as an overlay.
