# EC2 Staging Deployment

This project is set up for an EC2 staging deployment with:

- Django backend served by `gunicorn`
- Angular frontend served by `nginx`
- `nginx` reverse proxying `/api/` to Django
- Angular using relative API base URL `/api/`

Frontend project path used locally:

- `C:\educure\Finacc\accountproject`

Backend project path used locally:

- `C:\educure\finacc_new\Finacc`

Suggested EC2 target paths:

- Backend repo: `/home/ubuntu/finacc/Finacc`
- Python venv: `/home/ubuntu/finacc/venv`
- Angular publish directory: `/var/www/finacc-staging`

## 1. EC2 Packages

On Ubuntu EC2:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx postgresql postgresql-contrib
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

## 2. Backend Setup

Clone or copy the backend repo:

```bash
mkdir -p /home/ubuntu/finacc
cd /home/ubuntu/finacc
git clone <your-backend-repo-url> Finacc
python3 -m venv /home/ubuntu/finacc/venv
source /home/ubuntu/finacc/venv/bin/activate
pip install --upgrade pip
pip install -r /home/ubuntu/finacc/Finacc/requirements.txt
```

Create the environment file:

```bash
cp /home/ubuntu/finacc/Finacc/.env.example /home/ubuntu/finacc/Finacc/.env
nano /home/ubuntu/finacc/Finacc/.env
```

At minimum, set:

```env
SECRET_KEY=replace-with-real-secret
DEBUG=False
ALLOWED_HOSTS=staging.yourdomain.com
CORS_ORIGIN_ALLOW_ALL=False
CORS_ALLOWED_ORIGINS=https://staging.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://staging.yourdomain.com
DB_NAME=FA
DB_USER=postgres
DB_PASSWORD=replace-db-password
DB_HOST=127.0.0.1
DB_PORT=5432
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=False
```

Run Django setup:

```bash
cd /home/ubuntu/finacc/Finacc
source /home/ubuntu/finacc/venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check
```

## 3. Gunicorn Service

Copy the service file:

```bash
sudo cp /home/ubuntu/finacc/Finacc/deploy/ec2/gunicorn.service /etc/systemd/system/finacc-gunicorn.service
sudo systemctl daemon-reload
sudo systemctl enable finacc-gunicorn
sudo systemctl start finacc-gunicorn
sudo systemctl status finacc-gunicorn
```

If your EC2 username or paths are different, update:

- `User`
- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

## 4. Angular Build

On the machine where the Angular project exists:

```bash
cd /path/to/accountproject
npm ci
npm run build -- --configuration production
```

Build output:

```text
dist/my-app/browser
```

Upload the contents of `dist/my-app/browser` to EC2:

```bash
sudo mkdir -p /var/www/finacc-staging
sudo rsync -av --delete dist/my-app/browser/ ubuntu@<ec2-public-host>:/var/www/finacc-staging/
```

## 5. Nginx

Copy the nginx config:

```bash
sudo cp /home/ubuntu/finacc/Finacc/deploy/ec2/nginx-staging.conf /etc/nginx/sites-available/finacc-staging
```

Update:

- `server_name`
- frontend root if needed
- media/static paths if your backend path differs

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/finacc-staging /etc/nginx/sites-enabled/finacc-staging
sudo nginx -t
sudo systemctl restart nginx
```

## 6. Security Group

Open:

- `80` for HTTP
- `443` for HTTPS if SSL is enabled
- `22` for SSH

Do not expose PostgreSQL publicly unless absolutely required.

## 7. Recommended Next Step

After staging works on HTTP, add HTTPS with Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d staging.yourdomain.com
```

Then update `.env`:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

## 8. Smoke Test

Check:

- Angular site opens
- page refresh works on deep routes
- `/api/auth/...` requests reach Django
- login works
- static files load
- media files load
- `python manage.py check` passes
- `sudo systemctl status finacc-gunicorn` is healthy
- `sudo nginx -t` passes
