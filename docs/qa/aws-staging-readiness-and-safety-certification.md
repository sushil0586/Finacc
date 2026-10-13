# Finacc AWS Staging Readiness And Safety Certification

Date: 2026-10-12  
Baseline used: Phase 2C local performance certification and P0 pre-staging certification  
Local verified database: `finacc_perf_local`  
AWS safety verdict: **BLOCKED pending deployed-environment verification**

This document prepares the AWS production-like staging environment and records what is already verified locally versus what must be proved after the AWS stack is deployed. No AWS resources were provisioned by this certification, no production systems were accessed, and no load tests were executed.

## Executive Decision

| Gate | Status | Evidence / condition |
|---|---|---|
| Local Docker baseline | **PASS** | Docker services healthy; strict safety audit passed locally with `ready=true`, `13` verified, `0` blocked. |
| P0 financial correctness baseline | **PASS** | `425` targeted financial/GST tests passed in `440.882s`; see `docs/qa/finacc-p0-pre-staging-certification.md`. |
| AWS topology prepared | **PASS / DOCUMENTED** | Minimal production-like topology and deployment checklist defined below. |
| AWS environment safety certification | **BLOCKED** | No AWS-hosted strict audit, DB identity, storage identity, network-boundary proof or provider-sandbox proof was executed in this run. |
| Load-test permission | **BLOCKED** | Do not run Locust or filing-adjacent tests until every AWS safety gate below passes. |

Final recommendation: **Do not start AWS load tests yet.** Proceed with AWS staging deployment only after explicit infrastructure approval, then run the safety-audit commands in this report and attach the outputs.

## Inspected Configuration

### Backend

| Component | Current repo evidence | Readiness note |
|---|---|---|
| Django settings | `FA/settings.py` uses env-driven PostgreSQL, Redis/LocMem cache, S3/local storage, HTTPS/cookie controls, GST provider flags and email config. | Suitable for staging if environment variables are locked down and audited. |
| Gunicorn | `deploy/ec2/gunicorn.service` runs `FA.wsgi:application` on `127.0.0.1:8000` with `3` workers and `120s` timeout. | Matches local three-worker certification baseline. |
| Nginx | `deploy/ec2/nginx-staging.conf` serves Angular, static/media, and proxies `/api/` to Gunicorn. | Good minimal EC2 pattern; staging domain and TLS must be updated. |
| Deployment scripts | `deploy/ec2/deploy_backend_staging.sh`, `deploy/ec2/deploy_frontend_staging.sh`, `staging_refresh_backend.sh`. | Reusable, but current host/key defaults must be parameterized for an approved AWS staging host. |
| Database | Env-driven PostgreSQL. Local Docker DB is `finacc_perf_local`; EC2 docs currently show placeholder `DB_NAME=FA`. | AWS staging DB name must be explicitly staging/perf named, not production-like. |
| Cache | Redis supported through `CACHE_BACKEND=redis`, `CACHE_LOCATION=redis://...`. | Required for multi-worker cache correctness. |
| Storage | Local or S3 via `FILE_STORAGE_BACKEND`. S3 settings support bucket/region/location and IAM role usage. | Use a staging-only bucket/prefix; never share production bucket or IAM role. |
| Background jobs | No Celery/RQ worker deployment was found. Platform expiry timers exist as systemd timers. | Do not assume async workers. Add a worker service only if a specific production workflow requires it. |

### Frontend

| Component | Current repo evidence | Readiness note |
|---|---|---|
| Angular build | `package.json` has `build`, `build:dev`, verification and Playwright scripts. | EC2 docs currently use `build:dev` because production Angular build is noted as blocked by strict-template issues. |
| Production config | `environment.prod.ts` sets `production: true`; API calls rely on relative `/api/`. | Good for same-origin Nginx deployment. |
| Nginx static hosting | Existing staging Nginx serves SPA routes and immutable chunks. | Works for EC2 single-host staging. |

### Local Safety Recheck

The local Docker environment was rechecked during this preparation:

- `docker compose -f docker-compose.perf.yml ps`: PostgreSQL and Redis healthy; web and nginx running.
- `audit_performance_staging --strict --allow-db-name finacc_perf_local --allow-db-host postgres`: `ready=true`, `verified_count=13`, `blocked_count=0`.

This proves the local certified baseline, not AWS isolation.

## Minimal AWS Staging Topology

### Cost-conscious first stage

Use this only for controlled staging validation, not production capacity claims.

| Layer | Recommended minimal AWS choice | Reason |
|---|---|---|
| Region | `ap-south-1` unless business requires another region | Aligns with India/GST users and common Mumbai-region latency expectations. |
| VPC | Dedicated staging VPC or isolated staging subnets in a non-production VPC | Prevent accidental production DB/cache/storage access. |
| Public entry | ALB or single EC2 public Nginx | ALB is cleaner for TLS and health checks; single EC2 Nginx is cheaper. |
| App host | EC2 `t4g.medium` or `t4g.large` Ubuntu | Start with `t4g.medium` only for light staging; use `t4g.large` if running app, Nginx and batch tasks together. |
| Django | Gunicorn 3 sync workers initially | Matches local certification; increase only after telemetry. |
| PostgreSQL | RDS PostgreSQL Single-AZ `db.t4g.medium`, gp3 storage | Production-like managed DB without Multi-AZ cost. Consider `db.t4g.large` if 25-user/report tests saturate memory or CPU. |
| Redis | ElastiCache Redis/Valkey `cache.t4g.micro` or `cache.t4g.small`, Single-AZ | Required for multi-worker cache behavior; small is safer for report-cache tests. |
| Static frontend | EC2 Nginx initially; S3+CloudFront later | EC2 Nginx minimizes moving parts for first staging gate. |
| Media/storage | Staging-only S3 bucket or EC2 EBS local media for first gate | S3 preferred for isolation/audit; local media acceptable for a short-lived cost gate. |
| Secrets | AWS Systems Manager Parameter Store or Secrets Manager | Avoid `.env` secrets committed or reused across environments. |
| Logs/metrics | CloudWatch Agent, RDS Enhanced Monitoring optional | Must capture app CPU/RAM, DB CPU/connections/locks, Redis memory, Nginx/Gunicorn logs. |
| Backups | RDS automated backups 7 days, manual snapshot before destructive test windows | Required before any seed/reset or write-load activity. |

### Network and security groups

| Security group | Inbound | Outbound |
|---|---|---|
| ALB / Nginx public | `443` from internet; temporary `80` only for redirect/cert issuance | App host only if ALB; internet for updates if needed. |
| App EC2 | SSH only from approved admin IP/VPN; `8000` only from Nginx/ALB or localhost | RDS, Redis, S3 endpoint, package repos. |
| RDS | `5432` only from app EC2 security group and approved admin bastion if needed | None beyond AWS-managed requirements. |
| Redis | `6379` only from app EC2 security group | None beyond AWS-managed requirements. |
| S3 | Block public access; access only via staging IAM role | N/A |

Prohibited:

- Public RDS or Redis.
- Shared production and staging DB credentials.
- Production S3 bucket or prefix reuse.
- Live GST provider credentials in staging.
- Wildcard CORS with credentials.

## Required AWS Environment Variables

Use unique staging values. Never copy production secrets.

```env
DEBUG=False
SECRET_KEY=<aws-staging-secret>
ALLOWED_HOSTS=staging.example.com
CORS_ORIGIN_ALLOW_ALL=False
CORS_ALLOWED_ORIGINS=https://staging.example.com
CSRF_TRUSTED_ORIGINS=https://staging.example.com
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
AUTH_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True

DB_NAME=finacc_aws_staging
DB_USER=finacc_staging_app
DB_PASSWORD=<staging-only-secret>
DB_HOST=<rds-staging-endpoint>
DB_PORT=5432
DB_CONN_MAX_AGE=0
DB_CONN_HEALTH_CHECKS=True
DB_APPLICATION_NAME=finacc-aws-staging

CACHE_BACKEND=redis
CACHE_LOCATION=redis://<elasticache-staging-endpoint>:6379/1

FILE_STORAGE_BACKEND=s3
AWS_STORAGE_BUCKET_NAME=finacc-staging-files
AWS_S3_REGION_NAME=ap-south-1
AWS_MEDIA_LOCATION=staging

EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend

MASTERGST_ENV=SANDBOX
WHITEBOOKS_BASE_URL=https://apisandbox.whitebooks.in
WHITEBOOKS_SANDBOX_MODE=True
WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE=False
WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE=False
WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE=False
WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE=False
WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE=False

FINACC_ENABLE_WRITE_TESTS=false
FINACC_ENABLE_LIFECYCLE_TESTS=false
FINACC_PERF_ALLOWED_DB_NAMES=finacc_aws_staging
FINACC_PERF_ALLOWED_DB_HOSTS=<rds-staging-hostname>
```

Important: the repository `.env.example` currently shows production provider defaults such as `MASTERGST_ENV=PRODUCTION`, `WHITEBOOKS_BASE_URL=https://api.whitebooks.in`, and `WHITEBOOKS_SANDBOX_MODE=False`. Do not use those values for performance staging.

## Deployment Instructions

These are preparation commands only. Execute after AWS resource approval.

### Backend

```bash
ssh ubuntu@<aws-staging-host>
cd /home/ubuntu/Finacc
git fetch --all
git checkout <approved-branch>
git pull origin <approved-branch>
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
sudo systemctl restart finacc-gunicorn
sudo systemctl status finacc-gunicorn --no-pager
sudo nginx -t
sudo systemctl reload nginx
```

### Frontend

Preferred after production build blockers are cleared:

```bash
cd /Users/ansh/finacc-angular/accountproject
npm ci
npm run build -- --configuration production
rsync -av --delete dist/my-app/browser/ ubuntu@<aws-staging-host>:/var/www/finacc-staging/
```

Current documented fallback:

```bash
npm run build:dev -- --no-progress
```

If the fallback is used, mark staging as functionally valid but not a production-build equivalence certification.

## AWS Safety Audit Commands

Run these only after deployment, from the AWS staging app host.

```bash
cd /home/ubuntu/Finacc
source venv/bin/activate
python manage.py audit_performance_staging \
  --json \
  --strict \
  --allow-db-name finacc_aws_staging \
  --allow-db-host <rds-staging-hostname> \
  > /tmp/finacc_aws_staging_safety_audit.json
```

Database identity:

```bash
python manage.py dbshell
select current_database(), current_user, inet_server_addr(), inet_server_port(), pg_size_pretty(pg_database_size(current_database()));
```

Migration and health:

```bash
python manage.py showmigrations --plan > /tmp/finacc_aws_staging_migration_plan.txt
python manage.py check > /tmp/finacc_aws_staging_django_check.txt
sudo systemctl status finacc-gunicorn --no-pager
sudo nginx -t
```

Provider safety proof:

```bash
python manage.py shell -c "from django.conf import settings; print(settings.MASTERGST_ENV, settings.WHITEBOOKS_SANDBOX_MODE, settings.WHITEBOOKS_BASE_URL, settings.WHITEBOOKS_ENABLE_GSTR1_SAVE_LIVE, settings.WHITEBOOKS_ENABLE_GSTR1_FILE_LIVE, settings.WHITEBOOKS_ENABLE_GSTR3B_SAVE_LIVE, settings.WHITEBOOKS_ENABLE_GSTR3B_OFFSET_LIVE, settings.WHITEBOOKS_ENABLE_GSTR3B_FILE_LIVE)"
```

Storage identity proof:

```bash
python manage.py shell -c "from django.conf import settings; print(getattr(settings, 'FILE_STORAGE_BACKEND', None), getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None), getattr(settings, 'AWS_MEDIA_LOCATION', None))"
```

Do not run Locust, seed/reset commands, filing prepare/submit/save/file flows, or write-load scenarios until these outputs are archived and reviewed.

## Staging Acceptance Gates

| Gate | Required evidence | Status now |
|---|---|---|
| Dedicated AWS account/VPC/subnets or isolated staging network | AWS console/CLI identifiers | **Blocked** |
| RDS endpoint is staging-only and non-public | RDS endpoint, SG rules, DB identity query | **Blocked** |
| Redis endpoint is staging-only and non-public | ElastiCache endpoint and SG rules | **Blocked** |
| S3 bucket/prefix is staging-only | Bucket name, policy, block-public-access proof | **Blocked** |
| No live GST filing route | Strict audit plus provider settings proof | **Blocked in AWS; pass locally** |
| No production credentials | Secrets inventory with redacted names/ARNs | **Blocked** |
| Migrations consistent | `showmigrations --plan`, `manage.py check` | **Blocked in AWS; pass locally** |
| Monitoring active | CloudWatch logs/metrics, RDS metrics, Redis metrics | **Blocked** |
| Recovery snapshot exists | RDS snapshot identifier and restore plan | **Blocked** |
| Load tests disabled until gate passes | `FINACC_ENABLE_WRITE_TESTS=false`, `FINACC_ENABLE_LIFECYCLE_TESTS=false` | **Blocked in AWS; pass locally** |

## Cost Estimate

These are planning bands, not measured bills. Validate with the AWS Pricing Calculator before approval. AWS bills RDS using DB instance hours, provisioned storage, provisioned IOPS where applicable, and backup/storage components. RDS gp3 is a recommended general-purpose storage type with baseline IOPS/throughput characteristics. S3 and ElastiCache pricing vary by region, storage, requests and node/serverless model. Sources: AWS RDS billing and PostgreSQL pricing, RDS storage docs, ElastiCache pricing, and S3 pricing.

| Topology | Monthly planning band | Notes |
|---|---:|---|
| Lowest-cost single EC2 only: app + PostgreSQL + Redis on one EC2 with EBS | USD `40-90` | Useful only for deployment smoke. Not production-like enough for DB isolation or RDS telemetry. |
| Recommended first production-like staging: EC2 app, RDS PostgreSQL Single-AZ, ElastiCache single node, staging S3 | USD `120-300` | Best balance for the current P100 dataset and controlled load gates. |
| Stronger staging: larger EC2, larger RDS, ElastiCache small/medium, ALB, richer CloudWatch retention | USD `250-600+` | Use if 25-user/report tests or P100 heavy reports saturate the first topology. |

Cost controls:

- Start Single-AZ; do not enable Multi-AZ until needed for HA drills.
- Use gp3, not provisioned IOPS, unless telemetry proves I/O saturation.
- Keep CloudWatch retention bounded.
- Use lifecycle policies for S3 evidence/log buckets.
- Stop or downsize EC2 when not testing if acceptable.

## Monitoring Checklist

Before load tests, verify:

- EC2 CPU, memory, disk and network metrics.
- Gunicorn access/error logs and worker restart count.
- Nginx access/error logs.
- RDS CPU, FreeableMemory, connections, locks, deadlocks, read/write IOPS, throughput, storage, WAL/checkpoint indicators where available.
- PostgreSQL `pg_stat_statements` enabled for query fingerprints.
- Redis/ElastiCache CPU, memory, evictions, connections, hit/miss rate.
- Application audit/error logs are captured without secrets.
- Load generator runs outside the app host or is separately measured.

## Blockers

| Blocker | Severity | Closure |
|---|---|---|
| No AWS-hosted strict safety audit output in this run | P0 | Run `audit_performance_staging` on AWS staging after deployment. |
| No AWS RDS/Redis/S3/network boundary evidence | P0 | Capture resource IDs, endpoints, security groups, bucket policy and DB identity. |
| `.env.example` contains production GST provider defaults | P0 for staging config | Override with sandbox/disabled values in AWS secrets; do not use example values as-is. |
| Angular production build is documented as blocked in deployment notes | P1 | Use `build:dev` only for staging smoke, or clear strict-template blockers before production-like frontend certification. |
| No asynchronous/background-worker deployment model identified | P1 | Keep out of staging scope unless workflows require it; document systemd timers separately. |

## PASS / BLOCKED Verdict

**Preparation: PASS.** The repository contains enough deployment tooling and safety controls to prepare a cost-conscious AWS staging environment.

**Environment safety certification: BLOCKED.** The AWS environment was not accessed or audited in this run. The next step requiring approval is AWS resource provisioning or access to the already deployed staging host, followed by the strict audit and identity checks above.

**Load testing: BLOCKED.** Do not execute Locust, financial write-load, fixture reset, or GST filing-adjacent tests until AWS safety certification passes with archived evidence.

## References

- AWS RDS billing components: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/User_DBInstanceBilling.html
- AWS RDS storage and gp3 guidance: https://docs.aws.amazon.com/us_en/AmazonRDS/latest/UserGuide/CHAP_Storage.html
- AWS RDS for PostgreSQL pricing: https://aws.amazon.com/rds/postgresql/pricing/
- AWS ElastiCache pricing: https://aws.amazon.com/elasticache/pricing/
- AWS S3 pricing: https://aws.amazon.com/s3/pricing/

