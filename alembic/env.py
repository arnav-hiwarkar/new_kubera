from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio

# Import all models so metadata is populated
from app.models.base import Base
from app.models.company import Company, CompanyKey, CompanyUser  # noqa
from app.models.auditor import Auditor  # noqa
from app.models.activity_log import ActivityLog  # noqa
from app.models.notification import Notification  # noqa

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Source the DB URL from application settings (DATABASE_URL) rather than the
# hardcoded alembic.ini value, so migrations hit the right host in every context:
# localhost:5433 on the host (from .env) and postgres:5432 inside Docker (from the
# compose override). `%%` escapes configparser interpolation.
from app.config import get_settings

config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    except Exception as exc:  # noqa: BLE001 - re-raised below unless recognised
        _explain_connection_failure(exc)
        raise
    finally:
        await connectable.dispose()


def _explain_connection_failure(exc: BaseException) -> None:
    """Turn the common startup failures into one actionable line.

    `api` runs `alembic upgrade head` before uvicorn, so a connection problem
    manifests as a container restart loop whose logs are ~80 lines of SQLAlchemy
    and asyncpg stack frames with the actual cause on the last line. The most
    common cause by far is rotating POSTGRES_PASSWORD in .env, which does NOT
    change the password of an already-initialised pgdata volume."""
    import sys

    text = f"{type(exc).__name__}: {exc}"
    if "password authentication failed" in text.lower():
        message = (
            "Postgres rejected the credentials in DATABASE_URL.\n"
            "  POSTGRES_PASSWORD only takes effect when the pgdata volume is first\n"
            "  created; changing it in .env does not change an existing database.\n"
            "  Point the running database at the new password with:\n"
            "    docker compose exec postgres psql -U <user> -d <db> \\\n"
            "      -c \"ALTER USER <user> WITH PASSWORD '<new-password>';\"\n"
            "  See docs/SECURITY_HARDENING.md."
        )
    elif "could not translate host name" in text.lower() or "connection refused" in text.lower():
        message = (
            "Could not reach Postgres at the host in DATABASE_URL.\n"
            "  Inside Docker the host must be `postgres`, not `localhost` —\n"
            "  docker-compose.yml sets this; check for a stray override."
        )
    else:
        return

    print(
        "\n" + "=" * 72 + "\n"
        "  Kubera: database migration could not start\n" + "=" * 72 + "\n"
        f"  {message}\n" + "=" * 72 + "\n",
        file=sys.stderr,
        flush=True,
    )


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
