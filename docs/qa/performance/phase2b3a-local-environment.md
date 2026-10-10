# Finacc Phase 2B.3A - Production-Like Local Environment Setup

Date: 2026-10-10  
Scope: local-only production-like environment setup; no high-concurrency load; no destructive seed/reset  
Verdict: **Blocked for runtime smoke because Docker is not installed/available on this machine**

## Objective

Prepare a fully isolated, repeatable local performance environment using Docker Compose so Phase 2B can proceed without cloud deployment. The stack is designed to run only local services with disposable PostgreSQL and Redis state, safe integration settings, and a fail-closed safety audit.

## Configuration Inventory

| Component | Existing evidence | Phase 2B.3A action |
| --- | --- | --- |
| Django | `FA/settings.py`, PostgreSQL settings, Redis cache support, side-effect flags | Reused settings through safe local-only env |
| Gunicorn | `deploy/ec2/gunicorn.service` uses 3 workers and timeout 120 | Mirrored in Docker `CMD` with 3 workers, timeout 120 |
| PostgreSQL | Django uses env-driven PostgreSQL config | Added local `postgres:16-alpine` service with DB `finacc_perf_local` |
| Redis/cache | Redis supported via `CACHE_BACKEND=redis` | Added local `redis:7-alpine` service and `redis://redis:6379/1` namespace |
| Nginx | `deploy/ec2/nginx-staging.conf` proxies `/api/` to Gunicorn | Added local Nginx config proxying to `web:8000` |
| Background jobs | EC2 deploy installs platform expiry timers; no Celery config found | No background worker container added; timers remain out of scope locally |
| Angular | Angular app exists outside backend repo at `/Users/ansh/finacc-angular/accountproject` | Not built into this backend compose stack; Nginx validates API/proxy behavior only |
| Locust | Existing `perf/locust/locustfile.py` and env examples | Reused later against `http://localhost:18080`; no load run in this phase |

## Added Local Performance Stack

Files added:

```text
Dockerfile.perf
docker-compose.perf.yml
perf/docker/.env.perf-local
perf/docker/entrypoint.sh
perf/docker/nginx.conf
```

Service layout:

| Service | Image/build | Local port | Purpose |
| --- | --- | --- | --- |
| `postgres` | `postgres:16-alpine` | `15432` | Disposable performance DB |
| `redis` | `redis:7-alpine` | `16379` | Multi-worker cache backend |
| `web` | `Dockerfile.perf` | `18000` | Django/Gunicorn app |
| `nginx` | `nginx:1.27-alpine` | `18080` | Local reverse proxy |

Persistent Docker volumes:

```text
finacc_perf_postgres
finacc_perf_media
finacc_perf_static
```

## Safety Controls

The local env is intentionally separate from production:

- DB name: `finacc_perf_local`
- DB user: `finacc_perf`
- DB host inside compose: `postgres`
- Redis namespace: `redis://redis:6379/1`
- Hosts limited to local/container names.
- Email backend is `locmem`.
- Whitebooks is sandbox-routed.
- Whitebooks live GSTR save/file/offset flags are false.
- MasterGST environment is `SANDBOX`.
- File storage is local.
- Locust write/lifecycle flags are false by default.

The `web` container entrypoint runs:

```bash
python manage.py audit_performance_staging \
  --strict \
  --allow-db-name "$DB_NAME" \
  --allow-db-host "$DB_HOST"
```

If the identity or integration-safety gates fail, the application container exits before migrations or Gunicorn start.

## Startup

From backend root:

```bash
docker compose -f docker-compose.perf.yml up --build -d postgres redis
docker compose -f docker-compose.perf.yml up --build -d web nginx
```

Expected URLs after startup:

```text
Gunicorn direct: http://localhost:18000
Nginx proxy:     http://localhost:18080
Nginx health:    http://localhost:18080/healthz
Swagger:         http://localhost:18080/swagger/
```

## Health Checks

```bash
docker compose -f docker-compose.perf.yml ps
docker compose -f docker-compose.perf.yml logs --tail=100 web
docker compose -f docker-compose.perf.yml exec web python manage.py audit_performance_staging --strict --allow-db-name finacc_perf_local --allow-db-host postgres
docker compose -f docker-compose.perf.yml exec web python manage.py check
docker compose -f docker-compose.perf.yml exec web python manage.py showmigrations --plan | head -40
docker compose -f docker-compose.perf.yml exec redis redis-cli -n 1 ping
curl -fsS http://localhost:18080/healthz
curl -fsS http://localhost:18080/swagger/ >/dev/null
```

## Shutdown And Cleanup

Stop services without deleting state:

```bash
docker compose -f docker-compose.perf.yml down
```

Delete disposable local performance state:

```bash
docker compose -f docker-compose.perf.yml down -v
```

Do not run reset/seed commands against any database unless `audit_performance_staging --strict` passes for that exact DB name and host.

## Smoke Verification Attempt

Docker availability check:

```bash
docker --version && docker compose version
```

Observed result:

```text
zsh:1: command not found: docker
```

Because Docker is unavailable, the compose stack was not built or started. Therefore the following are **not executed**:

- container connectivity validation;
- PostgreSQL container health check;
- Redis container health check;
- Django migrations inside container;
- Gunicorn multi-worker runtime validation;
- Nginx proxy smoke test.

Static validation completed:

- Docker/compose files were created.
- `audit_performance_staging` is integrated into the container entrypoint and health check.
- Safe local-only env values were configured.
- Gunicorn settings mirror the current EC2 staging service shape: 3 workers, timeout 120.

## CPU/RAM And Local Limitations

The compose stack is intended for controlled local readiness and smoke testing only. It does not certify production capacity.

Recommended minimum local Docker allocation before smoke:

| Resource | Recommended minimum |
| --- | --- |
| CPU | 4 vCPU |
| RAM | 8 GB |
| Disk free | 20 GB |

Expected local limits:

- App, DB, Redis, Nginx, and load generator may compete for the same laptop CPU/RAM.
- Local filesystem latency is not representative of production storage.
- Docker Desktop resource caps can dominate PostgreSQL and Gunicorn behavior.
- Angular browser performance is separate from this backend/API stack unless the frontend is added later.

## Remaining Blockers

P0:

- Docker is not installed/available, so runtime smoke verification could not be executed.

P1:

- Full deterministic small/medium/large tenant fixture generator is still pending.
- Background timer behavior is not represented in local compose.
- Angular production static build is not included in this backend-only compose stack.

## Phase 2B.3A Verdict

**Environment files prepared, runtime setup blocked.**

Next recommended step: install/start Docker Desktop or provide an available Docker engine, then run the startup and health-check commands above. After the stack passes the safety audit, migrations, Redis ping, Nginx health, and Swagger smoke, proceed to fixture seeding design. Do not run high-concurrency load or destructive reset yet.
