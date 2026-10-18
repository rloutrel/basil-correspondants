# Basil — Correspondants

Basil (Basil — Assistant Synthétique à Intelligence Libre; English: Synthetic
Assistant with Free Intelligence) is a personal platform combining several
standalone components. This repository is the **correspondence component**: it
manages interactions with the outside world through *correspondants* —
external websites or services we exchange information with.

Each correspondant has **capabilities**: configurable instances of
code-defined **capability types**. The current catalog ships two types:

- **read-page** — access a page of the correspondant's website via a headless
  browser (Playwright) and extract information defined by CSS/XPath selectors,
  from a URL template.
- **parse-mail** — extract structured information from a raw email using a
  deterministic, template-based matcher: sender/subject/body match rules plus
  regex extraction rules. Multiple mail templates can exist per correspondant,
  ordered by priority; the first matching template wins. No AI.

The service is **generic**: everything site-specific is configuration data
(the first correspondant, `freelancermap`, is pure configuration — no
hard-coded business logic). The current phase is rules-based only; AI-powered
capabilities may be added later as new capability types.

The full specification of the capability system lives in
[docs/capability-spec.md](docs/capability-spec.md).

## Features

- **Capability catalog**: code-defined capability types (`read-page`,
  `parse-mail`) with explicit JSON input, output and configuration schemas,
  materialized into the database by a data migration.
- **Per-correspondant configuration**: capability instances validated at save
  time against their type's configuration schema (invalid configuration can
  never be persisted through any write path).
- **Capabilities API**: `GET /correspondants/{name}/capacities` with a
  `verbose` mode listing the REST resources of each capability, plus detail
  and execute endpoints. Consistent with the planned MCP exposure
  (`basil://correspondants/{name}/capacities` resource, one tool per
  capability).
- **Deterministic parse-mail engine**: pure functions of
  `(raw email, config)` — unit-tested against fixture emails, no network, no
  AI.
- **Execution log**: every capability execution is recorded with its input,
  output, status and duration.
- **Django admin** for debugging and configuration.

## API overview

```
GET  /api/correspondants/{name}/capacities           list enabled capabilities
GET  /api/correspondants/{name}/capacities?verbose=1  … with REST resources
GET  /api/correspondants/{name}/capacities/{cap}     detail: schemas + masked config
POST /api/correspondants/{name}/capacities/{cap}/execute  run a capability
```

The execute endpoint validates its payload against the capability type's
input schema (400 on failure), runs the capability and returns its output
(502 on infrastructure failure). Unknown or disabled correspondants and
capabilities return 404.

## Installation

### With Docker (recommended)

Requirements: Docker and Docker Compose.

```bash
git clone https://github.com/rloutrel/basil-correspondants.git
cd basil-correspondants
cp .env.example .env        # edit DJANGO_SECRET_KEY and credentials
docker compose up --build -d
```

The entrypoint runs migrations and `collectstatic` automatically, then starts
the server. The application is available at
[http://localhost:8000](http://localhost:8000). PostgreSQL data is persisted
in the `postgres_data` named volume.

The published host port is configurable with `WEB_PORT` (default `8000`). To
publish nothing on the host — e.g. behind a reverse proxy on an internal
Docker network — apply the `docker-compose.no-ports.yml` override.

### Without Docker

Requirements: Python 3.12+, a PostgreSQL server.

```bash
git clone https://github.com/rloutrel/basil-correspondants.git
cd basil-correspondants
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # point POSTGRES_* (or DATABASE_URL) at your server
set -a; source .env; set +a # or export the variables manually
python manage.py migrate
python manage.py collectstatic
python manage.py runserver
```

### Creating a superuser (admin)

```bash
python manage.py createsuperuser             # non-Docker
docker compose exec web python manage.py createsuperuser  # Docker
```

The admin is available at [http://localhost:8000/admin/](http://localhost:8000/admin/).

## Configuring correspondants and capabilities

In the Django admin, create a **correspondant** (name, base URL), then add
**capability** instances:

- a `read-page` capability with a URL template (`/projects/{reference}`)
  and CSS/XPath selectors;
- one or more `parse-mail` capabilities, one per mail kind: match rules on
  sender/subject/body (`exact`, `contains` or `regex`, AND-combined) and
  regex extraction rules. Set `priority` so the most specific templates are
  tried first; the first matching template wins.

All configuration is validated against the capability type's schema before
being saved; regexes are compiled and validated at save time.

## Testing

The suite covers the JSON-schema subset validator, the capability catalog
sync, model constraints (uniqueness, save-time config validation, protected
catalog rows, cascades), the deterministic parse-mail engine (matching,
AND-combination, capture-group semantics, priority ordering, first-match-wins)
and the capacities/execute endpoints (ordering, verbose mode, 404 handling,
secret masking). Playwright, IMAP/mail origins and MCP are always mocked —
no test ever talks to a real server. The suite runs against PostgreSQL (there
is no SQLite fallback).

Non-Docker:

```bash
export POSTGRES_HOST=localhost POSTGRES_DB=basil_correspondants \
       POSTGRES_USER=basil POSTGRES_PASSWORD=basil
python manage.py test
```

Docker:

```bash
docker compose exec web python manage.py test
```

## Languages

The interface is internationalised and ships English, German and French
catalogs (`django.po` files under `locale/`). UI labels are rendered in
French via i18n; `LANGUAGE_CODE = "en-gb"`.

## Roadmap

- **Playwright driver** for `read-page` (the adapter boundary is frozen;
  tests mock it).
- **MCP exposure**: capabilities as tools, the capacities list as a
  `basil://correspondants/{name}/capacities` resource.
- **UI**: daily-use page (correspondants, capacities, execution log) and a
  configuration page, HTMX + Alpine.js, dark/light theme.
- **AI-powered capabilities**: later, as new capability types.

See the open questions in the
[specification](docs/capability-spec.md#8-open-questions) for decisions
still to be made.

## Basil ecosystem

This component is part of the Basil ecosystem, alongside
[basil-mail](https://github.com/rloutrel/basil-mail) (mail collection and
organization), basil-chambellan (authentication and AI model access),
basil-chancelier (calendars and contacts), basil-scribe (writing assistance)
and basil-concierge (orchestration). It is fully standalone, but designed to
cooperate with the other components.
