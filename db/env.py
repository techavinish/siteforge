"""Alembic runtime — connects wherever DATABASE_URL points.

Local dev:   postgresql://siteforge:siteforge_dev@localhost:5432/siteforge
Cloud (via proxy): postgresql://app:<from-secret-manager>@localhost:6543/siteforge
Same migrations either way — the schema has one definition.
"""

import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ["DATABASE_URL"]


def run_migrations_offline() -> None:
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
