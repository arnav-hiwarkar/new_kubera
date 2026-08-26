import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATE = REPO_ROOT / "ops" / "kubera-migrate.sh"


def run(args, cwd=None):
    cwd = cwd or REPO_ROOT
    env = dict(os.environ)
    env["HOME"] = str(cwd)
    return subprocess.run(
        ["bash", str(MIGRATE), *args],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


def test_requires_target_arg():
    r = run([])
    assert r.returncode == 1
    assert "usage" in r.stderr.lower()


def test_invalid_target_rejected():
    r = run(["not-a-host-string"])
    assert r.returncode == 1
    assert "user@host" in r.stderr.lower()


def test_missing_env_aborts(tmp_path):
    r = run(["ash@203.0.113.10"], cwd=tmp_path)
    assert r.returncode == 1
    assert ".env not found" in r.stderr


def test_dry_run_shows_key_lifecycle_rsync_and_remote_call(tmp_path):
    sandbox = tmp_path
    (sandbox / ".env").write_text("POSTGRES_USER=u\nROOT_MASTER_KEK=x\nDOMAIN=lh\n")
    (sandbox / "docker-compose.yml").write_text("services: {}\n")
    r = run(["--dry-run", "--domain", "new.example", "ash@203.0.113.10"],
            cwd=sandbox)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    # Throwaway key lifecycle: generate, install, remove.
    assert out.index("ssh-keygen") < out.index("authorized_keys")
    assert out.index("authorized_keys") < out.index("sed -i")
    assert "kubera-migrate-" in out  # unique key comment used for removal
    # Transfer: bundle + repo tree with excludes, direct to staging dirs.
    assert "rsync" in out
    assert "--exclude .venv" in out
    assert "--exclude node_modules" in out
    assert "--exclude .git" in out
    assert "kubera-staging/bundle" in out
    assert "kubera-staging/repo" in out
    # Remote invocation carries domain + bundle path.
    assert "kubera-import.sh" in out
    assert "--domain" in out and "new.example" in out
    # Cutover checklist printed.
    assert "DNS" in out
