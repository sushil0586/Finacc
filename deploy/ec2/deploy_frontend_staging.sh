#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Staging frontend deploy helper for Git Bash
# Update these values only if your staging server/path changes.
# ---------------------------------------------------------------------------
ANGULAR_PROJECT_PATH="${ANGULAR_PROJECT_PATH:-/c/educure/Finacc/accountproject}"
PEM_PATH="${PEM_PATH:-$HOME/.ssh/bansalrenu.pem}"
REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_HOST="${REMOTE_HOST:-16.16.166.34}"
REMOTE_WEB_ROOT="${REMOTE_WEB_ROOT:-/var/www/accerio}"
REMOTE_DJANGO_MEDIA="${REMOTE_DJANGO_MEDIA:-/home/ubuntu/Finacc/media}"

# Use dev build for now because production build is currently blocked by
# unrelated strict-template issues in the frontend codebase.
BUILD_COMMAND="${BUILD_COMMAND:-npm.cmd run build:dev -- --no-progress}"
BUILD_OUTPUT_PATH="$ANGULAR_PROJECT_PATH/dist/my-app/browser"

echo "Building Angular app..."
cd "$ANGULAR_PROJECT_PATH"
eval "$BUILD_COMMAND"

if [ ! -d "$BUILD_OUTPUT_PATH" ]; then
  echo "Build output not found: $BUILD_OUTPUT_PATH" >&2
  exit 1
fi

echo "Uploading build files to staging..."
scp -i "$PEM_PATH" -r "$BUILD_OUTPUT_PATH"/* "$REMOTE_USER@$REMOTE_HOST:$REMOTE_WEB_ROOT/"

echo "Running remote post-deploy steps..."
ssh -i "$PEM_PATH" "$REMOTE_USER@$REMOTE_HOST" "
set -e
sudo mkdir -p '$REMOTE_WEB_ROOT'
sudo mkdir -p '$REMOTE_DJANGO_MEDIA'
if [ -d '$REMOTE_WEB_ROOT/media' ]; then
  sudo cp -r '$REMOTE_WEB_ROOT/media/.' '$REMOTE_DJANGO_MEDIA/'
fi
sudo nginx -t
sudo systemctl reload nginx
echo 'Frontend deploy complete.'
"

echo
echo "Staging frontend deploy completed successfully."
echo "Open: http://accerio.in"
