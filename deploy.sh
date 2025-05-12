#!/bin/bash
# deploy.sh
set -e  # Exit immediately if any command fails

# Install dependencies
pip install -r requirements.txt

# Run database migrations (if using Alembic)
alembic upgrade head

# Seed the database (only if SEED_DB=true)
if [ "$SEED_DB" = "true" ]; then
    echo "🏗️ Starting database seeding..."
    python -m src.core.database.seeddb
else
    echo "🔄 Skipping database seeding (SEED_DB not set to 'true')"
fi

# Start the FastAPI application
uvicorn src.main:app --host 0.0.0.0 --port $PORT