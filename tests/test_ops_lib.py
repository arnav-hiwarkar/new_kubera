import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB = REPO_ROOT / "ops" / "lib.sh"


def bash(script: str, **kw) -> subprocess.CompletedProcess:
    """Run a bash snippet with ops/lib.sh sourced."""
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"\n{script}'],
        capture_output=True, text=True, **kw,
    )


class TestLogging:
    def test_log_goes_to_stderr(self):
        r = bash('log hello')
        assert r.returncode == 0
        assert "[kubera-ops] hello" in r.stderr

    def test_die_exits_1_with_message(self):
        r = bash('die boom')
        assert r.returncode == 1
        assert "ERROR: boom" in r.stderr


class TestHashing:
    def test_sha256_of_known_value(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("kubera\n")
        r = bash(f'sha256_of "{f}"')
        # sha256 of "kubera\n"
        assert r.stdout.strip() == (
            "f8f3a94768b581ca276e315ff1c7239502baeeef394790f32d402eee78c37f6b"
        )

    def test_hash_cmd_reports_something(self):
        r = bash('hash_cmd >/dev/null && echo ok')
        assert r.returncode == 0


class TestLoadEnvAndKek:
    def test_load_env_exports_vars_and_kek_fingerprint(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("ROOT_MASTER_KEK=abc123\nDOMAIN=localhost\n")
        r = bash(f'load_env "{env}"\nkek_fingerprint')
        assert r.returncode == 0
        # sha256("abc123")[:16]
        assert r.stdout.strip() == "6ca13d52ca70c883"

    def test_apply_domain_rewrites_line(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("DOMAIN=localhost\nOTHER=1\n")
        r = bash(f'apply_domain "{env}" audit.example.com\ncat "{env}"')
        assert r.returncode == 0
        assert "DOMAIN=audit.example.com" in r.stdout
        assert "OTHER=1" in r.stdout

    def test_apply_domain_errors_when_absent(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("OTHER=1\n")
        r = bash(f'apply_domain "{env}" x.test')
        assert r.returncode == 1


class TestBundleChecks:
    def _bundle(self, tmp_path):
        b = tmp_path / "bundle"
        b.mkdir()
        (b / "db.dump").write_bytes(b"db")
        (b / "vault.tar.gz").write_bytes(b"v")
        (b / "env").write_text("ROOT_MASTER_KEK=x\n")
        (b / "manifest.json").write_text("{}")
        return b

    def test_verify_bundle_passes_and_checksums_roundtrip(self, tmp_path):
        b = self._bundle(tmp_path)
        r = bash(f'write_checksums "{b}" && verify_bundle "{b}"')
        assert r.returncode == 0, r.stderr
        assert (b / "sha256sums.txt").exists()

    def test_verify_bundle_fails_on_corruption(self, tmp_path):
        b = self._bundle(tmp_path)
        bash(f'write_checksums "{b}"')
        (b / "db.dump").write_bytes(b"TAMPERED")
        r = bash(f'verify_bundle "{b}"')
        assert r.returncode == 1
        assert "checksum" in r.stderr.lower()

    def test_verify_bundle_fails_on_missing_artifact(self, tmp_path):
        b = self._bundle(tmp_path)
        bash(f'write_checksums "{b}"')
        (b / "env").unlink()
        r = bash(f'verify_bundle "{b}"')
        assert r.returncode == 1


class TestManifest:
    def test_json_write_and_read_roundtrip(self, tmp_path):
        b = tmp_path / "bundle"
        b.mkdir()
        counts = "companies,3\ndocuments,42\n"
        r = bash(
            f'json_write_manifest "{b}" deadbeef fp1234 99 "{counts}"'
            f' && json_field "{b}/manifest.json" "row_counts[\'companies\']"'
            f' && json_field "{b}/manifest.json" "git_sha"'
            f' && json_field "{b}/manifest.json" "vault_file_count"'
        )
        assert r.returncode == 0, r.stderr
        lines = r.stdout.strip().splitlines()
        assert lines[0] == "3"
        assert lines[1] == "deadbeef"
        assert lines[2] == "99"


class TestRequireRepo:
    def test_passes_when_env_and_compose_present(self, tmp_path):
        (tmp_path / ".env").write_text("X=1\n")
        (tmp_path / "docker-compose.yml").write_text("services: {}\n")
        r = bash('require_repo', cwd=str(tmp_path))
        assert r.returncode == 0

    def test_fails_without_compose_file(self, tmp_path):
        (tmp_path / ".env").write_text("X=1\n")
        r = bash('require_repo', cwd=str(tmp_path))
        assert r.returncode == 1
        assert "docker-compose.yml" in r.stderr


class TestDryRun:
    def test_dr_run_executes_when_not_dry(self):
        r = bash('DRY_RUN=0\ndr_run touch /dev/null && echo ran')
        assert "ran" in r.stdout

    def test_dr_run_prints_instead_when_dry(self):
        r = bash('DRY_RUN=1\ndr_run touch /nonexistent-dir/x')
        assert r.returncode == 0
        assert "DRYRUN:" in r.stdout
        assert "ran" not in r.stdout
