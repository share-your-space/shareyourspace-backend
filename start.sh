#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
poetry run alembic upgrade head

# Start the application
echo "Starting the application..."
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 