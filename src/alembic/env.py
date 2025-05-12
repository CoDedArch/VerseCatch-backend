from logging.config import fileConfig
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
import sys
import os

# Add your project directory to the Python path
sys.path.append(os.getcwd())

# Import your SQLAlchemy Base and models
from core.database import Base
from core.config import settings
from apps.requotes.models import *  # Import all your models
from apps.requotes.models import *  # Import all your models

# This is the Alembic Config object, which provides access to the values within the .ini file.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata
target_metadata = Base.metadata

# Define the database URL

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.APOSTGRES_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = create_async_engine(settings.APOSTGRES_DATABASE_URL)

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn, target_metadata=target_metadata
            )
        )

        async with connection.begin():
            await connection.run_sync(context.run_migrations)

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())