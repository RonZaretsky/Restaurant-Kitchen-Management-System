#!/bin/sh
# Container entrypoint for the backend.
#
# Applies any pending Alembic revisions and only then starts the API. The schema is
# managed here, as an explicit step before the app boots, never inside the FastAPI
# lifespan. Compose gates this container on the Postgres healthcheck, so the
# database is already accepting connections by the time the upgrade runs.
#
# --no-dev keeps the runtime resolution identical to the image build, so pytest and
# the rest of the dev group never reach the running container.

set -e

echo "Applying database migrations..."
uv run --no-dev alembic upgrade head

echo "Starting the API..."
exec uv run --no-dev python main.py
