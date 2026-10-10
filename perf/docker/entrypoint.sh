#!/usr/bin/env bash
set -euo pipefail

if [[ "${DB_HOST:-}" != "" ]]; then
  echo "Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT:-5432}..."
  until nc -z "$DB_HOST" "${DB_PORT:-5432}"; do
    sleep 1
  done
fi

echo "Running performance-staging safety audit..."
python manage.py audit_performance_staging \
  --strict \
  --allow-db-name "${DB_NAME:-}" \
  --allow-db-host "${DB_HOST:-}"

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application: $*"
exec "$@"
