#!/bin/bash

# If SERVER_ENVIRONMENT is local, use mock PropelAuth
if [ "$SERVER_ENVIRONMENT" = "local" ]; then
    echo "Using mock PropelAuth for local environment"
    cp /workdir/mock/propelauth_fastapi_mock.py /workdir/.venv/lib/python3.12/site-packages/propelauth_fastapi/__init__.py
fi

# Wait for database to be ready (if using external DB)
echo "Waiting for database to be ready..."
sleep 5

# Start the application (migrations and seeding handled in startup event if AUTO_SEED=true)
exec uvicorn aci.server.main:app --proxy-headers --forwarded-allow-ips=* --host 0.0.0.0 --port 8000 --no-access-log
