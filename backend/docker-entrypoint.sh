#!/bin/sh
# Start the API. Migrations run first unless RUN_MIGRATIONS=false; disable them when
# several instances start at once and run `alembic upgrade head` separately.
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

# X-Forwarded-For is trusted only from FORWARDED_ALLOW_IPS.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-server-header
