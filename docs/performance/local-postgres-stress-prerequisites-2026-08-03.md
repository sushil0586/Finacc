# Local Postgres Stress Prerequisites

Last updated: 2026-08-03

## Purpose

Provide a clean preflight checklist before running higher-user Locust write or mixed stress profiles on local Finacc environments.

This exists because the August 3, 2026 purchase `100-user / 2-minute` isolated draft-write run failed primarily due to:
- `FATAL: sorry, too many clients already`
- secondary `deadlock detected` signals under saturation

So the first question before any high-tier rerun should be:
- is the application slow?
- or is the local Postgres/dev-server stack already capped?

## Confirm Current Local Capacity

Run:

```bash
cd Finacc
source venv/bin/activate
python manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute('show max_connections'); print('max_connections=', c.fetchone()[0]); c.execute(\"select count(*) from pg_stat_activity where datname=current_database()\"); print('active_db_connections=', c.fetchone()[0])"
```

Current observed local baseline on August 3, 2026:
- `max_connections=100`

That is too tight for repeated `100-user` write-tier runs when:
- Django is using the development server
- authentication hits the database on every request
- Locust is driving concurrent create/save/detail flows

## Recommended App-Level Settings

These are now configurable through environment variables:

```env
DB_POOL_ENABLED=False
DB_POOL_MIN_SIZE=4
DB_POOL_MAX_SIZE=24
DB_POOL_TIMEOUT_SECONDS=10
DB_POOL_MAX_WAITING=64
DB_CONN_MAX_AGE=0
DB_CONN_HEALTH_CHECKS=True
DB_CONNECT_TIMEOUT_SECONDS=5
DB_APPLICATION_NAME=finacc-django
```

Notes:
- `DB_POOL_ENABLED`
  - keep this `False` for normal local development
  - switch it `True` for higher-user stress reruns on local Postgres
  - Django 5.2 + psycopg3 can then reuse a bounded client pool instead of opening a fresh burst of connections
- `DB_POOL_MIN_SIZE` / `DB_POOL_MAX_SIZE`
  - these define the pool floor and ceiling
  - for local stress, a bounded pool is usually safer than allowing request concurrency to map directly to raw Postgres clients
- `DB_POOL_TIMEOUT_SECONDS` / `DB_POOL_MAX_WAITING`
  - these control how long callers wait for a pooled connection and how many can queue
  - they are useful for surfacing capacity pressure as controlled backpressure instead of immediate `too many clients already`
- `DB_CONN_MAX_AGE=0`
  - must stay `0` when Django-side pooling is enabled
  - Django's PostgreSQL backend rejects pooling if persistent connections are also enabled
- `DB_CONN_HEALTH_CHECKS=True`
  - helps Django detect broken stale connections before reuse
- `DB_CONNECT_TIMEOUT_SECONDS=5`
  - fails faster when the DB is saturated
- `DB_APPLICATION_NAME`
  - makes connection tracing easier in Postgres tools

These settings improve observability and connection hygiene, but they do not replace real database capacity planning.

Suggested local stress profile:

```env
DB_POOL_ENABLED=True
DB_POOL_MIN_SIZE=4
DB_POOL_MAX_SIZE=16
DB_POOL_TIMEOUT_SECONDS=15
DB_POOL_MAX_WAITING=128
DB_CONN_MAX_AGE=0
```

This does not make local Postgres production-grade, but it usually gives a much cleaner signal than opening one short-lived client burst per request wave.

## Recommended Local Execution Mode

Do not use the Django development server for serious stress tiers.

Prefer a bounded WSGI/ASGI runtime such as `gunicorn` with an explicit worker model, for example:

```bash
cd Finacc
source venv/bin/activate
gunicorn FA.wsgi:application --bind 127.0.0.1:8000 --workers 4 --threads 8 --timeout 120
```

Why:
- a bounded worker model is easier to reason about than the dev server under heavy concurrency
- it gives a cleaner mapping between application concurrency and database connection pressure

## Recommended Database Strategy For Higher Tiers

For realistic `100+` concurrent user write tests, use at least one of these:

1. Raise local Postgres capacity.
2. Put PgBouncer in front of Postgres.
3. Move the run to a staging stack that already has production-like pooling and worker limits.

Minimum practical guidance:
- if `max_connections` is still `100`, do not treat `100-user` write failures as a pure module defect
- first verify whether the DB is exhausting connection slots

## What To Check During A Failing Run

Check logs for:
- `too many clients already`
- `deadlock detected`
- long auth failures before business view code runs

The authentication path is especially important because DB saturation can start failing requests before the purchase, sales, or voucher business logic even begins.

## Practical Tier Guidance

Use this as the default interpretation model:

- `20 to 50 users`
  - acceptable for local code-path comparison work
  - useful for optimization A/B reruns
- `100 users write-heavy`
  - only meaningful if connection capacity is known to be sufficient
  - otherwise results mix app behavior with infrastructure ceiling

## Next-Step Rule

Before any new high-tier write rerun:

1. Check `max_connections`.
2. Run on `gunicorn` instead of `runserver`.
3. Confirm whether PgBouncer or higher DB capacity is available.
4. Only then compare latency or failure deltas across code changes.
