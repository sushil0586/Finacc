**Daily Staging Deploy**
Use these helpers for day-to-day staging updates on `accerio.in`.

**Files Added**
- `deploy/ec2/deploy_frontend_staging.ps1`
- `deploy/ec2/deploy_backend_staging.ps1`
- `deploy/ec2/deploy_frontend_staging.sh`
- `deploy/ec2/deploy_backend_staging.sh`
- `deploy/ec2/staging_refresh_backend.sh`

**1. Frontend Deploy From Your Windows Machine**
This script:
- builds Angular
- uploads the build to `/var/www/accerio`
- copies Angular font files from frontend `media/` into Django `media/`
- reloads Nginx

Run from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\ec2\deploy_frontend_staging.ps1
```

If your key path, host, or Angular path changes, update the variables at the top of:

`deploy/ec2/deploy_frontend_staging.ps1`

**Git Bash version**
Run from Git Bash:

```bash
cd /c/educure/finacc_new/Finacc
bash ./deploy/ec2/deploy_frontend_staging.sh
```

Recommended SSH key location for Git Bash scripts:

```bash
~/.ssh/bansalrenu.pem
```

**2. Backend Refresh On EC2**
Copy the script once to EC2 if needed:

```bash
scp -i /c/pem/bansalrenu.pem deploy/ec2/staging_refresh_backend.sh ubuntu@16.16.166.34:/home/ubuntu/Finacc/
```

Then on EC2:

```bash
cd /home/ubuntu/Finacc
chmod +x staging_refresh_backend.sh
./staging_refresh_backend.sh
```

This script:
- runs migrations
- runs `collectstatic`
- runs Django checks
- restarts Gunicorn
- reloads Nginx

**3. Backend Deploy From Your Windows Machine**
This script:
- connects to EC2
- pulls the latest backend code from git
- installs requirements
- runs migrations
- runs `collectstatic`
- runs checks
- ensures media subfolders are writable (`barcodes`, `products`, `purchase`)
- restarts Gunicorn
- reloads Nginx

Run from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\ec2\deploy_backend_staging.ps1
```

If your server branch, key path, host, or backend path changes, update the variables at the top of:

`deploy/ec2/deploy_backend_staging.ps1`

**Git Bash version**
Run from Git Bash:

```bash
cd /c/educure/finacc_new/Finacc
bash ./deploy/ec2/deploy_backend_staging.sh
```

**4. Recommended Daily Flow**
If only Angular changed:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\ec2\deploy_frontend_staging.ps1
```

or in Git Bash:

```bash
bash ./deploy/ec2/deploy_frontend_staging.sh
```

If only Django changed:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\ec2\deploy_backend_staging.ps1
```

or in Git Bash:

```bash
bash ./deploy/ec2/deploy_backend_staging.sh
```

If both changed:

1. Deploy backend code to EC2
2. Run backend deploy script
3. Run frontend deploy script from Windows

**5. One-Time Useful Global Setup**
On a fresh server/database:

```bash
python manage.py migrate
python manage.py seed_india_geography
python manage.py seed_entity_master_data
python manage.py seed_withholding
```

**6. Important Current Note**
Frontend script uses:

```powershell
npm.cmd run build:dev -- --no-progress
```

That is intentional for now because the production Angular build is still blocked by unrelated strict-template compile issues in other screens.
