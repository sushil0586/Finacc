$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Staging backend deploy helper
# Update these values only if your staging server/path changes.
# ---------------------------------------------------------------------------
$PemPath = "C:\pem\bansalrenu.pem"
$RemoteUser = "ubuntu"
$RemoteHost = "16.16.166.34"
$RemoteProjectDir = "/home/ubuntu/Finacc"
$RemoteBranch = "master"
$RemoteService = "finacc-gunicorn"

Write-Host "Deploying backend to staging..." -ForegroundColor Cyan

$remoteCommand = @"
set -e
cd '$RemoteProjectDir'

if [ -d .git ]; then
  echo 'Pulling latest backend code...'
  git fetch --all
  git checkout '$RemoteBranch'
  git pull origin '$RemoteBranch'
else
  echo 'No git repository found in $RemoteProjectDir'
  exit 1
fi

if [ -f 'venv/bin/activate' ]; then
  . 'venv/bin/activate'
else
  echo 'Virtual environment not found at venv/bin/activate'
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
sudo systemctl restart '$RemoteService'
sudo systemctl status '$RemoteService' --no-pager

echo 'Reloading Nginx...'
sudo nginx -t
sudo systemctl reload nginx

echo 'Backend deploy complete.'
"@

& ssh -i $PemPath "${RemoteUser}@${RemoteHost}" $remoteCommand

Write-Host ""
Write-Host "Staging backend deploy completed successfully." -ForegroundColor Green
