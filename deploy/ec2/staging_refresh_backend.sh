#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/Finacc}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/venv}"
GUNICORN_SERVICE="${GUNICORN_SERVICE:-finacc-gunicorn}"

cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"

echo "Applying migrations..."
python manage.py migrate

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Running Django system checks..."
python manage.py check

echo "Restarting gunicorn..."
sudo systemctl restart "$GUNICORN_SERVICE"
sudo systemctl status "$GUNICORN_SERVICE" --no-pager

echo "Reloading nginx..."
sudo nginx -t
sudo systemctl reload nginx

echo "Backend refresh completed."
