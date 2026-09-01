import glob
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "kubera",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "nightly-backup": {
            "task": "app.worker.nightly_backup",
            "schedule": crontab(hour=2, minute=0),  # 2 AM UTC daily
        }
    },
)


def pg_dump_target(database_url: str) -> tuple[list[str], dict[str, str]]:
    """Translate SQLAlchemy's DATABASE_URL into pg_dump arguments plus the
    environment that carries the password.

    Two things this exists to prevent:

    1. pg_dump does not understand SQLAlchemy's `+driver` dialect suffix. Handed
       `postgresql+asyncpg://user:pw@postgres:5432/kubera` it does NOT fail on the
       scheme — it ignores the URI entirely and falls back to a local Unix socket,
       which does not exist in the worker container. The nightly database backup
       therefore failed every night and the error was only printed, so the backup
       directory looked healthy because the vault tarball beside it succeeded.
    2. A URL passed as an argument puts the database password in the process list,
       readable by anything that can run `ps` in the container. The password goes
       through PGPASSWORD instead.
    """
    parts = urlsplit(database_url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(f"DATABASE_URL is not a PostgreSQL URL (scheme: {scheme!r})")

    database = unquote((parts.path or "").lstrip("/"))
    if not database:
        raise RuntimeError("DATABASE_URL does not name a database")

    args: list[str] = []
    if parts.hostname:
        args += ["-h", parts.hostname]
    if parts.port:
        args += ["-p", str(parts.port)]
    if parts.username:
        args += ["-U", unquote(parts.username)]
    args += ["-d", database]

    env = {"PGPASSWORD": unquote(parts.password)} if parts.password else {}
    return args, env


def prune_old_backups(backup_dir: str, retention_days: int) -> list[str]:
    """Delete backup artifacts older than the retention window.

    Without this the vault tarball alone grows by the full size of the vault every
    night, and the first symptom is Postgres failing to write because the disk is
    full."""
    if retention_days <= 0:
        return []
    cutoff = time.time() - retention_days * 86400
    removed: list[str] = []
    for pattern in ("db_backup_*.dump", "db_backup_*.sql", "vault_backup_*.tar.gz"):
        for path in glob.glob(os.path.join(backup_dir, pattern)):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed.append(path)
            except OSError as exc:
                logger.warning("could not prune %s: %s", path, exc)
    return removed


@celery_app.task
def nightly_backup():
    """Dump the database and the vault to BACKUP_PATH, then prune old artifacts.

    Raises on failure rather than printing: a backup that fails silently is worse
    than no backup, because it is indistinguishable from a working one until the
    day it is needed."""
    backup_dir = settings.BACKUP_PATH
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    db_backup_file = os.path.join(backup_dir, f"db_backup_{timestamp}.dump")
    vault_backup_file = os.path.join(backup_dir, f"vault_backup_{timestamp}.tar.gz")

    # --- Database. -Fc matches the format ops/kubera-import.sh restores from. ---
    args, pg_env = pg_dump_target(settings.DATABASE_URL)
    result = subprocess.run(
        ["pg_dump", *args, "-Fc", "-f", db_backup_file],
        capture_output=True,
        text=True,
        env={**os.environ, **pg_env},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    if not os.path.exists(db_backup_file) or os.path.getsize(db_backup_file) == 0:
        raise RuntimeError(f"pg_dump reported success but {db_backup_file} is empty")

    # --- Vault ---
    vault_path = settings.VAULT_STORAGE_PATH
    vault_bytes = 0
    if os.path.isdir(vault_path):
        parent, name = os.path.split(vault_path.rstrip("/"))
        result = subprocess.run(
            ["tar", "-czf", vault_backup_file, "-C", parent, name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"vault tar failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        vault_bytes = os.path.getsize(vault_backup_file)
    else:
        logger.warning("vault path %s does not exist; skipping vault backup", vault_path)

    pruned = prune_old_backups(backup_dir, settings.BACKUP_RETENTION_DAYS)

    logger.info(
        "nightly backup complete: db=%s (%d bytes) vault=%s (%d bytes) pruned=%d",
        db_backup_file, os.path.getsize(db_backup_file),
        vault_backup_file, vault_bytes, len(pruned),
    )
    return {
        "status": "success",
        "timestamp": timestamp,
        "db_backup": db_backup_file,
        "db_bytes": os.path.getsize(db_backup_file),
        "vault_backup": vault_backup_file if vault_bytes else None,
        "vault_bytes": vault_bytes,
        "pruned": len(pruned),
    }


# Import celery tasks so worker discovers them upon startup
import app.services.email.tasks  # noqa: F401

