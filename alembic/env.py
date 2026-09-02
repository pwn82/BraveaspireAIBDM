"""
Alembic env — reuses the app's DATABASE_URL and engine so migrations honor
the same cloud-detection / SQL-Server / SQLite selection as the runtime.

Highlights:
  • Never reads sqlalchemy.url from alembic.ini (kept blank on purpose).
  • Enables `render_as_batch=True` on SQLite so ALTER TABLE works.
  • target_metadata = Base.metadata → autogenerate compares against models.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

# Ensure the project root is importable no matter where alembic is invoked from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Import runtime engine + metadata — this is the whole point of this file.
from app.database.db import engine as app_engine, DATABASE_URL       # noqa: E402
from app.database.models import Base                                  # noqa: E402

config = context.config

# Alembic logging config (optional).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_IS_SQLITE = DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection ('alembic upgrade head --sql')."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_IS_SQLITE,   # required for ALTER on SQLite
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB using the app's already-configured engine."""
    with app_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_IS_SQLITE,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
