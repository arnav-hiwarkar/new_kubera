import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPORT = REPO_ROOT / "ops" / "kubera-import.sh"


def make_bundle(tmp_path, tamper=None, drop=None):
    src = tmp_path / "bundle-src"
    src.mkdir()
    files = {
        "db.dump": b"PGDMP",
        "vault.tar.gz": b"VAULT",
        "env": b"POSTGRES_USER=kubera\nROOT_MASTER_KEK=abc123\nDOMAIN=localhost\n",
        "manifest.json": b'{"row_counts": {"companies": 3}, "vault_file_count": 9,'
                         b' "kek_fingerprint": "fp"}',
    }
    if drop:
        del files[drop]
    for name, data in files.items():
        (src / name).write_bytes(data)
    bundle = tmp_path / "bundle"
    shutil.copytree(src, bundle)
    if tamper:
        (bundle / tamper).write_bytes(b"TAMPERED")
    return bundle


def write_checksums(bundle):
    subprocess.run(
        ["bash", "-c",
         f'source "{REPO_ROOT}/ops/lib.sh"; write_checksums "{bundle}"'],
        check=True, capture_output=True,
    )


def run(bundle, args=(), cwd=None):
    cwd = cwd or bundle.parent
    env = dict(os.environ)
    env["HOME"] = str(cwd)
    return subprocess.run(
        ["bash", str(IMPORT), str(bundle), *args],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


def test_missing_bundle_dir_fails_cleanly(tmp_path):
    r = run(tmp_path / "nope")
    assert r.returncode == 1
    assert "not found" in r.stderr.lower()


def test_relative_bundle_path_supported(tmp_path):
    """DR use-case: run from another dir with ./bundle — path must be absolutized."""
    bundle = make_bundle(tmp_path)
    write_checksums(bundle)
    # cwd = tmp_path, so './bundle' resolves; script invoked by absolute path.
    r = subprocess.run(
        ["bash", str(REPO_ROOT / "ops" / "kubera-import.sh"), "./bundle", "--dry-run"],
        capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr
    assert str(bundle) in r.stdout  # plan references the ABSOLUTE bundle path


def test_corrupt_checksum_aborts_before_docker(tmp_path):
    bundle = make_bundle(tmp_path)
    write_checksums(bundle)
    (bundle / "db.dump").write_bytes(b"TAMPERED")
    r = run(bundle)
    assert r.returncode == 1
    assert "checksum" in r.stderr.lower()
    # Nothing was restored/mutated in cwd.
    assert not (bundle.parent / "kubera").exists()


def test_missing_artifact_aborts(tmp_path):
    bundle = make_bundle(tmp_path, drop="env")
    r = run(bundle)
    assert r.returncode == 1
    assert "env" in r.stderr


def test_domain_rewrite_appears_in_dry_run_plan(tmp_path):
    bundle = make_bundle(tmp_path)
    write_checksums(bundle)
    r = run(bundle, args=["--domain", "audit.new.example", "--dry-run"])
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "DOMAIN=audit.new.example" in out
    # Ordering: setup before restore before full up before verify.
    # (rindex: the LAST "docker compose up -d" is start_stack's; an earlier
    #  one belongs to restore_vault's "up -d postgres".)
    assert out.index("get.docker.com") < out.index("pg_restore")
    assert out.index("pg_restore") < out.rindex("docker compose up -d")
    assert "readyz" in out
    # Idempotent restore + real health wait are part of the plan.
    # (%q quoting escapes spaces, so assert tokens, not the literal flag pair.)
    assert "clean" in out and "if-exists" in out
    assert "timeout 600s" in out
    assert out.index("readyz") < out.lower().index("verification")


def test_keep_bundle_flag_preserves_bundle_in_dry_run_plan(tmp_path):
    bundle = make_bundle(tmp_path)
    write_checksums(bundle)
    r_keep = run(bundle, args=["--dry-run"])
    r_drop = run(bundle, args=["--dry-run", "--keep-bundle"])
    assert "rm -rf" in r_keep.stdout          # default cleans bundle
    assert "rm -rf" not in r_drop.stdout      # kept
