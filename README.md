# NTS Pharmacy System — Multi-Tenant Pharmacy Management SaaS

Django + DRF + PostgreSQL (Neon) backend, React + TypeScript + Tailwind frontend. No Docker.
Status and roadmap: [IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md).

## Local development (Windows, no Docker)

Backend (Python 3.12+):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # set DATABASE_URL to your Neon string, or leave empty for local SQLite
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser   # creates a PLATFORM admin (no tenant)
.\.venv\Scripts\python manage.py runserver
.\.venv\Scripts\python -m pytest                    # run tests
```

Frontend (Node 20+):

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
npm test
```

Without `REDIS_URL`, cache/channels/Celery fall back to in-process dev equivalents. **Production requires Redis.**
The platform login is hidden: click the empty space in the home page navbar 5 times (or open `/platform/login`).

## Docs
- [System architecture](docs/SYSTEM_ARCHITECTURE.md) · [Tenant architecture](docs/TENANT_ARCHITECTURE.md)
- [Authentication & permissions](docs/AUTHENTICATION_AND_PERMISSIONS.md) · [Security](docs/SECURITY_ARCHITECTURE.md)
- [Environment variables](docs/ENVIRONMENT_VARIABLES.md)

Remaining documents from the spec (DATABASE_SCHEMA, API_DOCUMENTATION, INVENTORY/PRESCRIPTION/POS/PAYMENT workflows,
BACKUP_AND_RECOVERY, DEPLOYMENT_GUIDE) are written in the phase that implements each area.
