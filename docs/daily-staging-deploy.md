**Daily Staging Deploy**
Use these helpers for day-to-day staging updates on `accerio.in`.

**Current Staging Values**
- Host: `16.16.166.34`
- SSH user: `ubuntu`
- Backend path on server: `/home/ubuntu/Finacc`
- Frontend publish path on server: `/var/www/accerio`
- Django media path on server: `/home/ubuntu/Finacc/media`
- Gunicorn service: `finacc-gunicorn`
- Frontend local path: `/Users/ansh/finacc-angular/accountproject`
- Backend local path: `/Users/ansh/finacc-angular/finacc-django/Finacc`

**Files Added**
- `deploy/ec2/deploy_frontend_staging.ps1`
- `deploy/ec2/deploy_backend_staging.ps1`
- `deploy/ec2/deploy_frontend_staging.sh`
- `deploy/ec2/deploy_backend_staging.sh`
- `deploy/ec2/staging_refresh_backend.sh`

**0. Manual Step-By-Step Commands**

**Frontend Manual Deploy**
Run these commands from your local machine:

```bash
cd /Users/ansh/finacc-angular/accountproject
npm install
npm run build:dev -- --no-progress
scp -i ~/Downloads/bansalrenu.pem -r dist/my-app/browser/* ubuntu@16.16.166.34:/var/www/accerio/
ssh -i ~/Downloads/bansalrenu.pem ubuntu@16.16.166.34
```

Then on the server:

```bash
sudo mkdir -p /var/www/accerio
sudo mkdir -p /home/ubuntu/Finacc/media
if [ -d /var/www/accerio/media ]; then sudo cp -r /var/www/accerio/media/. /home/ubuntu/Finacc/media/; fi
sudo nginx -t
sudo systemctl reload nginx
exit
```

**Backend Manual Deploy**
Run these commands from your local machine:

```bash
ssh -i ~/Downloads/bansalrenu.pem ubuntu@16.16.166.34
```

Then on the server:

```bash
cd /home/ubuntu/Finacc
git fetch --all
git checkout master
git pull origin master
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
sudo mkdir -p /home/ubuntu/Finacc/media/barcodes
sudo mkdir -p /home/ubuntu/Finacc/media/products
sudo mkdir -p /home/ubuntu/Finacc/media/purchase
sudo chown -R ubuntu:www-data /home/ubuntu/Finacc/media
sudo find /home/ubuntu/Finacc/media -type d -exec chmod 775 {} \;
sudo find /home/ubuntu/Finacc/media -type f -exec chmod 664 {} \;
sudo systemctl restart finacc-gunicorn
sudo systemctl status finacc-gunicorn --no-pager
sudo nginx -t
sudo systemctl reload nginx
exit
```

**If Both Frontend And Backend Changed**
Run in this order:

1. Deploy backend first.
2. Confirm `python manage.py check` passes.
3. Confirm `sudo systemctl status finacc-gunicorn --no-pager` is healthy.
4. Deploy frontend after backend is healthy.
5. Open `http://accerio.in` and test login plus one API-backed screen.

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
~/Downloads/bansalrenu.pem
```

**2. Backend Refresh On EC2**
Copy the script once to EC2 if needed:

```bash
scp -i ~/Downloads/bansalrenu.pem deploy/ec2/staging_refresh_backend.sh ubuntu@16.16.166.34:/home/ubuntu/Finacc/
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

**7. Quick Verification**
After any deploy, verify:

```bash
ssh -i ~/Downloads/bansalrenu.pem ubuntu@16.16.166.34
sudo systemctl status finacc-gunicorn --no-pager
sudo nginx -t
exit
```

Then in browser verify:
- `http://accerio.in` opens
- login works
- one dashboard page loads
- `/api/` requests return expected responses
