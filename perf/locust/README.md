# Finacc Django Locust Starter

This is the backend performance test starter for Finacc (`/api/*` routes).

## Covered endpoints

- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/sales/invoices/`
- `GET /api/sales/settings/`
- optional `PATCH /api/sales/settings/` (disabled by default)
- optional sales invoice lifecycle (`confirm`, `post`, `reverse`) (disabled by default)

## Setup

```bash
cd perf/locust
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with staging/local credentials and IDs.
You can set these either in `perf/locust/.env` or backend root `.env` (`Finacc/.env`).

## Run

UI mode:

```bash
locust -f locustfile.py
```

Headless mode:

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m
```

Headless with report artifacts:

```bash
locust -f locustfile.py --headless --users 50 --spawn-rate 5 --run-time 5m \
  --csv results_read_50u_5m --html results_read_50u_5m.html
```

Use local Django host:

```bash
locust -f locustfile.py --host http://127.0.0.1:8000
```

## Important

- Keep `FINACC_ENABLE_WRITE_TESTS=false` unless you are in a safe staging DB.
- Keep `FINACC_ENABLE_LIFECYCLE_TESTS=false` unless you are in a safe staging DB.
- Start with read-heavy scenarios, then gradually add write endpoints.

## Enable Lifecycle Scenario

In `.env`:

```bash
FINACC_ENABLE_LIFECYCLE_TESTS=true
```

Then run a low load first:

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m
```

Run lifecycle-only profile (tag-based):

```bash
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 2m \
  --tags lifecycle --csv results_lifecycle_5u_2m --html results_lifecycle_5u_2m.html
```
