#!/bin/bash
# deploy.sh
set -e

pip install -r requirements.txt

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
    python <<EOF
import asyncio
from src.core.database.seeddb import main

async def run_seeding():
    await main()
    print('✅ Seeding completed')

asyncio.run(run_seeding())
EOF
else
    echo "🔄 Skipping database seeding (SEED_DB not set to 'true')"
fi

# Keep worker alive if needed (remove if one-time task)
while true; do
    sleep 3600  # Sleep for 1 hour
    echo "🔄 Background worker keep-alive"
done
