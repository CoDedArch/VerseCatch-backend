#!/bin/bash
# deploy.sh
set -e  # Exit immediately if any command fails

# Install dependencies
pip install -r requirements.txt

# Initialize database (critical step)
echo "🛠️ Initializing database..."
python -m src.core.database.init_db

# Only run migrations if alembic.ini exists
if [ -f "alembic.ini" ]; then
    echo "🔄 Running database migrations..."
    alembic upgrade head
else
    echo "⚠️ No alembic.ini found - skipping migrations"
fi

# Seed the database (only if SEED_DB=true)
if [ "$SEED_DB" = "true" ]; then
    echo "🏗️ Starting database seeding..."
    python -m src.core.database.seeddb
else
    echo "🔄 Skipping database seeding (SEED_DB not set to 'true')"
fi

# Start the FastAPI application
uvicorn src.main:app --host 0.0.0.0 --port $PORT
