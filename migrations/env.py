import os
from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = os.getenv("POSTGRES_SYNC_URL", "postgresql://akea_user:akea_password@localhost:5432/akea_db")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine

    url = os.getenv("POSTGRES_SYNC_URL", "postgresql://akea_user:akea_password@localhost:5432/akea_db")
    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
