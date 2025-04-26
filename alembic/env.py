import asyncio # Import asyncio
import os
import sys
from logging.config import fileConfig

# Explicitly load .env file before importing application modules
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import pool
# Use create_async_engine for async connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the app directory is in the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import application settings and Base model
# Now settings should correctly load variables from the .env file
from app.core.config import settings
from app.db.base_class import Base
# Import your models here so Base has them registered
from app.models import * # Import all models from the models package
# from app.models.item import Item # Example

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set the database URL directly in the config object from settings
# This ensures commands like 'revision' use the correct, environment-aware URL
# Convert Pydantic SecretStr to plain string if necessary
db_url = str(settings.DATABASE_URL)
config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the Base metadata object for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # Use the DATABASE_URL from application settings
    context.configure(
        url=db_url, # Use the db_url variable defined above
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# --- Start of modified run_migrations_online ---
def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # --- Print the DB URL being used for debugging ---
    # print(f"Attempting to connect to database: {db_url}") # Removed debug print
    # -----------------------------------------------

    # Create an async engine using the DATABASE_URL from settings
    connectable = create_async_engine(
        db_url, # Use the db_url variable defined above
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    # Dispose the engine
    await connectable.dispose()
# --- End of modified run_migrations_online ---


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Run the async online migration function using asyncio
    asyncio.run(run_migrations_online())
