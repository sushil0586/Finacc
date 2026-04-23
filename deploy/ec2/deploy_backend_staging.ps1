$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE"
    }
}

# ---------------------------------------------------------------------------
# Staging backend deploy helper
# Update these values only if your staging server/path changes.
# ---------------------------------------------------------------------------
$PemPath = Join-Path $HOME ".ssh\bansalrenu.pem"
$RemoteUser = "ubuntu"
$RemoteHost = "16.16.166.34"
$RemoteProjectDir = "/home/ubuntu/Finacc"
$RemoteBranch = "master"
$RemoteService = "finacc-gunicorn"

Write-Host "Deploying backend to staging..." -ForegroundColor Cyan

if (-not (Test-Path $PemPath)) {
    throw "SSH key not found at $PemPath"
}

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

echo 'Ensuring media directories are writable...'
sudo mkdir -p /home/ubuntu/Finacc/media/barcodes
sudo mkdir -p /home/ubuntu/Finacc/media/products
sudo mkdir -p /home/ubuntu/Finacc/media/purchase
sudo chown -R ubuntu:www-data /home/ubuntu/Finacc/media
sudo find /home/ubuntu/Finacc/media -type d -exec chmod 775 {} \;
sudo find /home/ubuntu/Finacc/media -type f -exec chmod 664 {} \;

echo 'Restarting Gunicorn...'
sudo systemctl restart '$RemoteService'
sudo systemctl status '$RemoteService' --no-pager

echo 'Reloading Nginx...'
sudo nginx -t
sudo systemctl reload nginx

echo 'Backend deploy complete.'
"@

Invoke-NativeCommand -FailureMessage "Backend deploy failed." -Command {
    ssh -i $PemPath "${RemoteUser}@${RemoteHost}" $remoteCommand
}

Write-Host ""
Write-Host "Staging backend deploy completed successfully." -ForegroundColor Green
