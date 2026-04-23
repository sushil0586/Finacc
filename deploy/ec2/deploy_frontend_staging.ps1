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
# Staging frontend deploy helper
# Update these values only if your staging server/path changes.
# ---------------------------------------------------------------------------
$AngularProjectPath = "C:\educure\Finacc\accountproject"
$PemPath = Join-Path $HOME ".ssh\bansalrenu.pem"
$RemoteUser = "ubuntu"
$RemoteHost = "16.16.166.34"
$RemoteWebRoot = "/var/www/accerio"
$RemoteDjangoMedia = "/home/ubuntu/Finacc/media"
$RemoteNginxSite = "accerio"

# Use dev build for now because production build is currently blocked by
# unrelated strict-template issues in the frontend codebase.
$BuildCommand = "npm.cmd run build:dev -- --no-progress"
$BuildOutputPath = Join-Path $AngularProjectPath "dist\my-app\browser"

Write-Host "Building Angular app..." -ForegroundColor Cyan
Push-Location $AngularProjectPath
try {
    Invoke-Expression $BuildCommand
}
finally {
    Pop-Location
}

if (-not (Test-Path $BuildOutputPath)) {
    throw "Build output not found: $BuildOutputPath"
}

if (-not (Test-Path $PemPath)) {
    throw "SSH key not found at $PemPath"
}

Write-Host "Uploading build files to staging..." -ForegroundColor Cyan
Invoke-NativeCommand -FailureMessage "Frontend upload failed." -Command {
    scp -i $PemPath -r "$BuildOutputPath\*" "${RemoteUser}@${RemoteHost}:${RemoteWebRoot}/"
}

Write-Host "Running remote post-deploy steps..." -ForegroundColor Cyan
$remoteCommand = @"
set -e
sudo mkdir -p '$RemoteWebRoot'
sudo mkdir -p '$RemoteDjangoMedia'
if [ -d '$RemoteWebRoot/media' ]; then
  sudo cp -r '$RemoteWebRoot/media/.' '$RemoteDjangoMedia/'
fi
sudo nginx -t
sudo systemctl reload nginx
echo 'Frontend deploy complete.'
"@

Invoke-NativeCommand -FailureMessage "Remote frontend post-deploy steps failed." -Command {
    ssh -i $PemPath "${RemoteUser}@${RemoteHost}" $remoteCommand
}

Write-Host ""
Write-Host "Staging frontend deploy completed successfully." -ForegroundColor Green
Write-Host "Open: http://accerio.in" -ForegroundColor Green
