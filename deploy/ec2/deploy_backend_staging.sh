#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Staging backend deploy helper for Git Bash
# Update these values only if your staging server/path changes.
# ---------------------------------------------------------------------------
PEM_PATH="${PEM_PATH:-$HOME/.ssh/bansalrenu.pem}"
REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-16.16.166.34}"
REMOTE_PROJECT_DIR="${REMOTE_PROJECT_DIR:-/home/ubuntu/Finacc}"
REMOTE_BRANCH="${REMOTE_BRANCH:-master}"
REMOTE_SERVICE="${REMOTE_SERVICE:-finacc-gunicorn}"

echo "Deploying backend to staging..."

ssh -i "$PEM_PATH" "$REMOTE_USER@$REMOTE_HOST" "
set -e
cd '$REMOTE_PROJECT_DIR'

if [ -d .git ]; then
  echo 'Pulling latest backend code...'
  git fetch --all
  git checkout '$REMOTE_BRANCH'
  git pull origin '$REMOTE_BRANCH'
else
  echo 'No git repository found in $REMOTE_PROJECT_DIR' >&2
  exit 1
fi

if [ -f 'venv/bin/activate' ]; then
  . 'venv/bin/activate'
else
  echo 'Virtual environment not found at venv/bin/activate' >&2
  exit 1
fi

echo 'Installing/updating Python dependencies...'
pip install -r requirements.txt

echo 'Applying database migrations...'
python manage.py migrate

echo 'Collecting static files...'
python manage.py collectstatic --noinput

echo 'Running Django system checks...'
python manage.py check

echo 'Restarting Gunicorn...'
sudo systemctl restart '$REMOTE_SERVICE'
sudo systemctl status '$REMOTE_SERVICE' --no-pager

echo 'Reloading Nginx...'
sudo nginx -t
sudo systemctl reload nginx

echo 'Backend deploy complete.'
"

echo
echo "Staging backend deploy completed successfully."
