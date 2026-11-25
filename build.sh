#!/usr/bin/env bash
# Render build: build the React app, copy it into the backend (served by Django/WhiteNoise), install deps, collect static, migrate.
set -o errexit
( cd frontend && npm ci && npm run build )
rm -rf backend/frontend_dist && cp -r frontend/dist backend/frontend_dist
cd backend
pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
# Neon: run migrations over the DIRECT (non-pooled) connection; the app itself uses the pooled DATABASE_URL.
DATABASE_URL="${DIRECT_DATABASE_URL:-$DATABASE_URL}" python manage.py migrate --noinput
python manage.py check --deploy || true
