import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORT = REPO_ROOT / "ops" / "kubera-export.sh"


def run(args, cwd=REPO_ROOT, env_extra=None):
    env = dict(os.environ)
    env.setdefault("HOME", str(cwd))
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(EXPORT), *args],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


def make_repo_root(tmp_path):
    """Minimal repo-root stand-in so require_repo passes."""
    (tmp_path / ".env").write_text(
        "POSTGRES_USER=kubera\nPOSTGRES_PASSWORD=pw\n"
        "POSTGRES_DB=kubera\nROOT_MASTER_KEK=abc123\nDOMAIN=localhost\n"
    )
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    return tmp_path


def test_missing_env_aborts_before_any_mutation(tmp_path):
    r = run(["--dest", str(tmp_path / "b")], cwd=tmp_path)
    assert r.returncode == 1
    assert ".env not found" in r.stderr


def test_dry_run_lists_full_sequence_without_executing(tmp_path):
    sandbox = make_repo_root(tmp_path)
    dest = tmp_path / "out"
    r = run(["--dest", str(dest), "--dry-run"], cwd=sandbox)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Sequence sanity: freeze writes before dumping; checksums after manifest.
    i_maint = out.index("DRYRUN: python3 maintenance.py on")
    i_stop = out.index("DRYRUN: docker compose stop api worker beat")
    i_dump = out.index("pg_dump")
    i_tar = out.index("tar czf")
    i_chk = out.lower().index("checksum")
    assert i_maint < i_stop < i_dump < i_tar < i_chk
    # Nothing was executed: dest was never created.
    assert not dest.exists()
    # Bundle path is echoed as final line for callers.
    assert str(dest) in out.strip().splitlines()[-1]


def test_no_maintenance_flag_skips_toggle(tmp_path):
    sandbox = make_repo_root(tmp_path)
    r = run(["--dest", str(tmp_path / "out"), "--dry-run",
             "--no-maintenance"], cwd=sandbox)
    assert r.returncode == 0
    assert "maintenance.py on" not in r.stdout


import shutil

import pytest


@pytest.mark.skipif(
    shutil.which("docker") is None or os.environ.get("KUBERA_OPS_ROUNDTRIP") != "1",
    reason="opt-in live-stack smoke: set KUBERA_OPS_ROUNDTRIP=1 with dev stack up",
)
class TestLiveExportSmoke:
    def test_export_produces_verifiable_bundle(self, tmp_path):
        r = run(["--dest", str(tmp_path / "bundle"), "--no-maintenance"])
        assert r.returncode == 0, r.stderr
        bundle = Path(r.stdout.strip().splitlines()[-1])
        assert (bundle / "db.dump").stat().st_size > 0
        assert (bundle / "vault.tar.gz").exists()
        manifest = (bundle / "manifest.json").read_text()
        assert '"kek_fingerprint"' in manifest
        # Checksum file validates.
        chk = subprocess.run(
            ["bash", "-c",
             f'source "{REPO_ROOT}/ops/lib.sh"; verify_bundle "{bundle}"'],
            capture_output=True, text=True,
        )
        assert chk.returncode == 0, chk.stderr
        # NOTE: export stops api/worker/beat on the dev stack — bring them back.
        subprocess.run(["docker", "compose", "up", "-d", "api", "worker", "beat"],
                       cwd=REPO_ROOT, capture_output=True)
