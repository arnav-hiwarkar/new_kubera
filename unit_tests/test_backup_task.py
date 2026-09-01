"""The nightly backup silently produced no database dump for months.

`pg_dump` handed a SQLAlchemy URL (`postgresql+asyncpg://...`) does not reject the
unknown `+asyncpg` dialect — it ignores the URI entirely and falls back to a local
Unix socket, which does not exist in the worker container. The task caught the
failure and only printed it, and the vault tarball beside it kept succeeding, so
the backup directory looked healthy.
"""

from __future__ import annotations

import os
import time

import pytest

from app.worker import pg_dump_target, prune_old_backups


class TestPgDumpTarget:
    def test_strips_the_sqlalchemy_dialect_suffix(self):
        args, _ = pg_dump_target("postgresql+asyncpg://kubera:pw@postgres:5432/kubera")
        assert args == ["-h", "postgres", "-p", "5432", "-U", "kubera", "-d", "kubera"]

    def test_plain_postgresql_scheme_also_works(self):
        args, _ = pg_dump_target("postgresql://kubera:pw@db:5432/kubera")
        assert "-h" in args and "db" in args

    def test_password_goes_to_the_environment_not_the_argument_list(self):
        """A URL in argv puts the database password in the container's process
        list, readable by anything that can run `ps`."""
        args, env = pg_dump_target("postgresql+asyncpg://kubera:s3cret@postgres:5432/kubera")
        assert env == {"PGPASSWORD": "s3cret"}
        assert "s3cret" not in " ".join(args)

    def test_percent_encoded_credentials_are_decoded(self):
        """A generated password may contain characters that must be URL-escaped;
        pg_dump needs the decoded value."""
        _, env = pg_dump_target("postgresql+asyncpg://u:p%40ss%2Fword@h:5432/db")
        assert env["PGPASSWORD"] == "p@ss/word"

    def test_missing_password_yields_no_pgpassword(self):
        _, env = pg_dump_target("postgresql://kubera@postgres:5432/kubera")
        assert env == {}

    def test_rejects_a_non_postgres_url(self):
        with pytest.raises(RuntimeError, match="not a PostgreSQL URL"):
            pg_dump_target("mysql://u:p@h:3306/db")

    def test_rejects_a_url_without_a_database_name(self):
        with pytest.raises(RuntimeError, match="does not name a database"):
            pg_dump_target("postgresql://u:p@h:5432/")


class TestPruneOldBackups:
    def _make(self, directory, name, age_days):
        path = directory / name
        path.write_bytes(b"x")
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
        return path

    def test_removes_artifacts_past_the_retention_window(self, tmp_path):
        stale = self._make(tmp_path, "db_backup_20260101_000000.dump", 30)
        fresh = self._make(tmp_path, "db_backup_20260901_000000.dump", 1)
        removed = prune_old_backups(str(tmp_path), retention_days=14)
        assert str(stale) in removed
        assert not stale.exists()
        assert fresh.exists()

    def test_prunes_vault_tarballs_too(self, tmp_path):
        """The vault tarball is a full copy of the vault every night — it is the
        artifact that actually fills the disk."""
        stale = self._make(tmp_path, "vault_backup_20260101_000000.tar.gz", 30)
        prune_old_backups(str(tmp_path), retention_days=14)
        assert not stale.exists()

    def test_prunes_the_legacy_sql_naming(self, tmp_path):
        """Backups written before the -Fc switch are named .sql and must still be
        cleaned up, or they linger forever."""
        stale = self._make(tmp_path, "db_backup_20260101_000000.sql", 30)
        prune_old_backups(str(tmp_path), retention_days=14)
        assert not stale.exists()

    def test_zero_retention_disables_pruning(self, tmp_path):
        ancient = self._make(tmp_path, "db_backup_20200101_000000.dump", 3650)
        assert prune_old_backups(str(tmp_path), retention_days=0) == []
        assert ancient.exists()

    def test_leaves_unrelated_files_alone(self, tmp_path):
        keep = self._make(tmp_path, "README.txt", 3650)
        prune_old_backups(str(tmp_path), retention_days=14)
        assert keep.exists()
