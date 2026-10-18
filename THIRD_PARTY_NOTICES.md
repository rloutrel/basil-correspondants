# Third-party notices

Basil — correspondants component is MIT-licensed. It depends on the following
permissively licensed third-party packages:

| Package | License | Notes |
|---|---|---|
| Django | BSD-3-Clause | Web framework, ORM, admin |
| psycopg2-binary | LGPL-3.0 (runtime dependency only, not distributed) | PostgreSQL adapter — Django's documented PostgreSQL driver; see note below |
| dj-database-url | BSD-2-Clause | DATABASE_URL parsing |

Everything else is the Python standard library (`email`, `re`, `json`).
Notably, JSON Schema validation is a hand-rolled subset validator
(`correspondants/schemas.py`) to keep the dependency stack fully
permissive-only.

**Note on psycopg2-binary:** it is licensed under LGPL-3.0, but it is used
strictly as an unmodified runtime dependency (installed from PyPI, never
distributed with this project) and is not linked statically — the LGPL
explicitly permits this. If you prefer a fully permissive stack, install the
Apache-2.0-licensed `psycopg` package instead; Django 5 supports it natively
(`pip install "psycopg[binary]"` and no other change is needed).
