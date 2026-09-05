from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from ansari.api.config import get_settings
from ansari.api.db import Base
from ansari.api.models import Deployment, Environment, PipelineRun, Project  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Honour a URL the caller already configured -- the test fixtures point Alembic
# at a throwaway database. Overwriting it unconditionally sent migrations to
# whatever ANSARI_DATABASE_URL named, which for a developer is their real
# database.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
