#!/bin/sh
set -e

python -m alembic upgrade head

exec python -m uvicorn main:app --host 0.0.0.0 --port "${APP_PORT:-8000}"
