"""Mediul Alembic. Migrările rulează ca `ama_owner` (AMA_DATABASE_OWNER_URL), nu ca rolul aplicației."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings

config = context.config


def _url() -> str:
    url = config.attributes.get("url")  # setat de teste; ocolește interpolarea din alembic.ini
    return str(url) if url else get_settings().database_owner_url


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
