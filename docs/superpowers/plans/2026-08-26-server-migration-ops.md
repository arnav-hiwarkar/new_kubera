# Server Migration & DR Ops Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command, checksum-verified migration of a running Kubera server to a bare Ubuntu server (data + secrets + code + stack startup), reusable as disaster-recovery backup/restore.

**Architecture:** Three bash scripts in a new `ops/` dir sharing `ops/lib.sh`. `kubera-export.sh` freezes writes and produces a bundle (Postgres `pg_dump -Fc`, vault tarball, `.env`, manifest, SHA256 sums). `kubera-migrate.sh` transfers bundle + repo tree server-to-server over SSH with a throwaway key, then remotely invokes `kubera-import.sh`, which sets up Docker, restores, starts, and verifies against the manifest. Spec: `docs/superpowers/specs/2026-08-26-server-migration-design.md`.

**Tech Stack:** Bash (Ubuntu 20.04–24.04 hosts), Docker Compose v2, rsync, SSH, Python 3 (present on hosts; used for JSON manifest read/write), pytest + subprocess for script tests.

## Global Constraints

- All ops scripts are `#!/usr/bin/env bash` with `set -euo pipefail`, run on the Docker **host** from the repository root (same as `python3 maintenance.py`, see README "Zero-downtime maintenance mode").
- Secrets discipline: never print `.env` values. Only ever print `kek_fingerprint` (first 16 hex chars of SHA256 of `ROOT_MASTER_KEK`).
- Bundle layout is fixed and referenced by name everywhere: `db.dump`, `vault.tar.gz`, `env`, `manifest.json`, `sha256sums.txt` inside `kubera-migration-<YYYYMMDD-HHMMSS>/`.
- Every mutating action goes through `dr_run` so `--dry-run` prints `DRYRUN:` + the command instead of executing it.
- Tests run with `uv run pytest <file> -v` (repo convention: pytest.ini has `asyncio_mode = auto`, `pythonpath = .`; scripts are tested via `subprocess` + bash sourcing, no Docker required except the opt-in smoke test in Task 5).
- Scripts must work whether `sha256sum` (Linux) or `shasum -a 256` (macOS) is available — handled once in `ops/lib.sh:hash_cmd`.
- Verification tables (confirmed models, used in manifests): `companies`, `documents`, `document_versions`, `audit_engagements`.
- Maintenance toggling reuses the existing host-side tool verbatim: `python3 maintenance.py on|off`.

---

### Task 1: Shared library `ops/lib.sh`

**Files:**
- Create: `ops/lib.sh`
- Test: `tests/test_ops_lib.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces (all sourced by Tasks 2–4):
  - `log MSG…` / `warn MSG…` / `die MSG…` — stderr logging; `die` exits 1.
  - `need_cmd CMD` — dies if `command -v CMD` fails.
  - `require_repo` — dies unless `.env` and `docker-compose.yml` exist in `$PWD` (ops scripts always operate on the current directory as repo root).
  - `load_env FILE` — sources a `.env`-style file with vars exported (`set -a`).
  - `hash_cmd` — echoes `sha256sum` or `shasum -a 256` (whichever exists).
  - `sha256_of FILE` — echoes hex digest.
  - `kek_fingerprint` — echoes first 16 hex chars of SHA256 of `$ROOT_MASTER_KEK` (must already be loaded via `load_env`).
  - `apply_domain ENV_FILE NEW_DOMAIN` — rewrites the `DOMAIN=` line in place.
  - `write_checksums BUNDLE_DIR` — writes `sha256sums.txt` covering `db.dump vault.tar.gz env manifest.json`.
  - `verify_bundle BUNDLE_DIR` — checks all five artifacts exist and `sha256sums.txt` matches; `die`s on failure.
  - `json_write_manifest BUNDLE_DIR GIT_SHA KEK_FP VAULT_FILES counts.csv` — writes `manifest.json`; `counts.csv` is `table,count` lines.
  - `json_field JSON_FILE PY_EXPR` — reads a value via `python3 -c` (e.g. `json_field m.json "row_counts['companies']"`).
  - `dr_run CMD…` — dry-run wrapper honoring global `DRY_RUN` (0/1).

- [ ] **Step 1: Write the failing test**

Create `tests/test_ops_lib.py`:

```python
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
            "e0ac0e87a592ff6a6f40bfe1d961eeb0f19a4aeb59cd5ee9d3f0a3c3fea377a9"
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
        r = bash('DRY_RUN=1\ndr_run touch /nonexistent-dir/x && echo ran')
        assert r.returncode == 0
        assert "DRYRUN:" in r.stdout
        assert "ran" not in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ops_lib.py -v`
Expected: FAIL — `ops/lib.sh` does not exist (source fails).

- [ ] **Step 3: Write the implementation**

Create `ops/lib.sh`:

```bash
#!/usr/bin/env bash
# Shared helpers for Kubera ops scripts (export/import/migrate).
# Source this file; do not execute it.
set -euo pipefail

log() { printf '[kubera-ops] %s\n' "$*" >&2; }
warn() { printf '[kubera-ops] WARN: %s\n' "$*" >&2; }
die() { printf '[kubera-ops] ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

# Ops scripts operate on the CURRENT directory as the repo root (README convention:
# run from the repository checkout), never on the script's own location.
require_repo() {
  [ -f .env ] || die ".env not found in $PWD (run from the repo root)"
  [ -f docker-compose.yml ] || die "docker-compose.yml not found in $PWD (run from the repo root)"
}

load_env() {
  local f="$1"
  [ -f "$f" ] || die ".env not found at $f"
  set -a
  # shellcheck disable=SC1090
  . "$f"
  set +a
}

hash_cmd() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf 'sha256sum'
  elif command -v shasum >/dev/null 2>&1; then
    printf 'shasum -a 256'
  else
    die "neither sha256sum nor shasum available"
  fi
}

sha256_of() {
  # shellcheck disable=SC2046
  $(hash_cmd) "$1" | awk '{print $1}'
}

kek_fingerprint() {
  [ -n "${ROOT_MASTER_KEK:-}" ] || die "ROOT_MASTER_KEK not set"
  printf '%s' "$ROOT_MASTER_KEK" | $(hash_cmd) | cut -c1-16
}

apply_domain() {
  local f="$1" d="$2"
  grep -q '^DOMAIN=' "$f" || die "DOMAIN line missing in $f"
  if [[ $(uname) == "Darwin" ]]; then
    sed -i '' "s|^DOMAIN=.*|DOMAIN=$d|" "$f"
  else
    sed -i "s|^DOMAIN=.*|DOMAIN=$d|" "$f"
  fi
}

# Fixed bundle artifact list (Global Constraint).
BUNDLE_ARTIFACTS=(db.dump vault.tar.gz env manifest.json)

write_checksums() {
  local dir="$1"
  (
    cd "$dir" || die "cannot cd $dir"
    for f in "${BUNDLE_ARTIFACTS[@]}"; do
      [ -f "$f" ] || die "missing bundle artifact: $f"
    done
    # shellcheck disable=SC2046
    $(hash_cmd) "${BUNDLE_ARTIFACTS[@]}" > sha256sums.txt
  )
}

verify_bundle() {
  local dir="$1" f
  for f in "${BUNDLE_ARTIFACTS[@]}" sha256sums.txt; do
    [ -f "$dir/$f" ] || die "bundle missing artifact: $f"
  done
  if ! (cd "$dir" && $(hash_cmd) -c sha256sums.txt --status); then
    die "bundle checksum mismatch — transfer corrupted or tampered; refusing to continue"
  fi
}

json_write_manifest() {
  local dir="$1" git_sha="$2" kek_fp="$3" vault_files="$4" counts_csv="$5"
  python3 - "$dir/manifest.json" "$git_sha" "$kek_fp" "$vault_files" "$counts_csv" <<'PYEOF'
import json, sys, datetime
path, git_sha, kek_fp, vault_files, counts_csv = sys.argv[1:6]
rows = {}
for line in counts_csv.splitlines():
    if not line.strip():
        continue
    table, count = line.split(",")
    rows[table] = int(count)
json.dump({
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "git_sha": git_sha,
    "kek_fingerprint": kek_fp,
    "vault_file_count": int(vault_files),
    "row_counts": rows,
}, open(path, "w"), indent=2)
print("wrote", path)
PYEOF
}

json_field() {
  local f="$1" expr="$2"
  python3 -c "import json,sys; print(eval(json.load(open(sys.argv[1]))$expr))" "$f" 2>/dev/null \
    || die "cannot read field $expr from $f"
}

# Dry-run wrapper: set DRY_RUN=1 to print instead of execute.
# Prints to STDOUT so orchestrators/tests can grep the full plan.
dr_run() {
  if [ "${DRY_RUN:-0}" = "1" ]; then
    printf 'DRYRUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}
```

Make it executable:

```bash
chmod +x ops/lib.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ops_lib.py -v`
Expected: PASS (all classes).

Note on the two hardcoded digests in tests: verify them locally before committing the test file:

```bash
printf 'kubera\n' | shasum -a 256     # must equal the digest in test_sha256_of_known_value
printf 'abc123'  | shasum -a 256     # must equal the digest prefix in test_load_env_exports_vars_and_kek_fingerprint
```

If your platform produces different values, fix the expected strings to the actual computed ones — the algorithm is what matters, not these literals.

- [ ] **Step 5: Commit**

```bash
git add ops/lib.sh tests/test_ops_lib.py
git commit -m "feat(ops): shared library for migration/DR scripts with tests"
```

---

### Task 2: Export script `ops/kubera-export.sh`

**Files:**
- Create: `ops/kubera-export.sh`
- Test: `tests/test_ops_export.py`

**Interfaces:**
- Consumes: everything from `ops/lib.sh` (Task 1).
- Produces:
  - CLI: `ops/kubera-export.sh [--dest DIR] [--no-maintenance] [--keep-live] [--dry-run]`
  - Behavior contract used by Tasks 3–5:
    - Creates bundle dir (default `$HOME/kubera-migration-<ts>`, honors `--dest`) containing exactly `db.dump vault.tar.gz env manifest.json sha256sums.txt`.
    - Prints the bundle path as the **last stdout line** (Tasks 3–5 capture it).
    - Order: maintenance on (unless `--no-maintenance`) → stop `api worker beat` → dump → tar → copy env → manifest → checksums → optionally restart + maintenance off (`--keep-live`).
    - Vault tar is created with contents rooted at `/data/vault` (`tar czf … -C /data/vault .`), so import extracts symmetrically.
    - Exit codes: 0 success; 1 any failure via `die`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ops_export.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ops_export.py -v`
Expected: FAIL — `ops/kubera-export.sh` does not exist.

- [ ] **Step 3: Write the implementation**

Create `ops/kubera-export.sh`:

```bash
#!/usr/bin/env bash
# Produce a verified Kubera bundle: Postgres dump + vault tarball + .env + manifest.
# Usage: ops/kubera-export.sh [--dest DIR] [--no-maintenance] [--keep-live] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

DEST=""
NO_MAINTENANCE=0
KEEP_LIVE=0
DRY_RUN="${DRY_RUN:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --no-maintenance) NO_MAINTENANCE=1; shift ;;
    --keep-live) KEEP_LIVE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done

require_repo
load_env "$PWD/.env"

TS="$(date +%Y%m%d-%H%M%S)"
BUNDLE="${DEST:-$HOME/kubera-migration-$TS}"
if [ "$DRY_RUN" != "1" ]; then
  mkdir -p "$BUNDLE"
  chmod 700 "$BUNDLE"
else
  echo "DRYRUN: mkdir -p $BUNDLE && chmod 700 $BUNDLE"
fi

if [ "$DRY_RUN" != "1" ]; then
  need_cmd docker
  dr_run docker compose up -d postgres
else
  echo "DRYRUN: docker compose up -d postgres"
fi

if [ "$NO_MAINTENANCE" != "1" ]; then
  dr_run python3 maintenance.py on
fi

if [ "$DRY_RUN" != "1" ]; then
  API_CID="$(docker compose ps -q api)"
  [ -n "$API_CID" ] || die "api container not found — is the stack up?"
else
  API_CID="DRYRUN-API-CID"
fi
dr_run docker compose stop api worker beat

# --- Database dump (custom format, compressed) ---
if [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: pg_dump -U \$POSTGRES_USER -Fc \$POSTGRES_DB > $BUNDLE/db.dump"
else
  log "dumping database..."
  dr_run docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
    > "$BUNDLE/db.dump"
fi

# --- Vault tarball (contents rooted at /data/vault) ---
if [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: tar czf $BUNDLE/vault.tar.gz via volumes-from $API_CID"
else
  log "archiving vault..."
  dr_run docker run --rm --volumes-from "$API_CID" alpine:3 \
    tar czf - -C /data/vault . > "$BUNDLE/vault.tar.gz"
fi

# --- Secrets ---
if [ "$DRY_RUN" != "1" ]; then
  cp "$ROOT/.env" "$BUNDLE/env"
  chmod 600 "$BUNDLE/env"
fi

if [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: write manifest.json + checksums for bundle artifacts"
else
  log "writing manifest..."
  GIT_SHA="$(git -C "$PWD" rev-parse HEAD 2>/dev/null || echo unknown)"
  KEK_FP="$(kek_fingerprint)"
  VAULT_FILES="$(docker run --rm --volumes-from "$API_CID" alpine:3 \
    sh -c 'find /data/vault -type f | wc -l')"
  COUNTS=""
  for t in companies documents document_versions audit_engagements; do
    c="$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
      "SELECT count(*) FROM $t")"
    COUNTS+="$t,$c"$'\n'
  done
  json_write_manifest "$BUNDLE" "$GIT_SHA" "$KEK_FP" "$VAULT_FILES" "$COUNTS" >/dev/null
  write_checksums "$BUNDLE"
  log "verification summary:"
  log "  vault files: $VAULT_FILES"
  log "  kek fingerprint: $KEK_FP"
fi

if [ "$KEEP_LIVE" = "1" ]; then
  dr_run docker compose up -d api worker beat
  if [ "$NO_MAINTENANCE" != "1" ]; then
    dr_run python3 maintenance.py off
  fi
else
  log "old stack left FROZEN (api/worker/beat stopped, maintenance on)."
  log "Re-run later with --keep-live semantics or restore service via:"
  log "  docker compose up -d api worker beat && python3 maintenance.py off"
fi

echo "$BUNDLE"
```

Make executable:

```bash
chmod +x ops/kubera-export.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ops_export.py -v`
Expected: PASS.

Note: `test_dry_run_lists_full_sequence_without_executing` asserts `dest` is never created, but the script above does `mkdir -p "$BUNDLE"` unconditionally. Adjust the script so directory creation is also gated: replace the unconditional `mkdir -p "$BUNDLE"` with:

```bash
if [ "$DRY_RUN" != "1" ]; then
  mkdir -p "$BUNDLE"
  chmod 700 "$BUNDLE"
fi
```

and guard the two `>` redirects shown above exactly as coded (the `[ -s … ] || true` line can then be removed).

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -q`
Expected: no failures introduced (pre-existing failures unrelated to `ops/` are acceptable; note them if seen).

- [ ] **Step 6: Commit**

```bash
git add ops/kubera-export.sh tests/test_ops_export.py
git commit -m "feat(ops): export script producing verified migration/DR bundles"
```

---

### Task 3: Import script `ops/kubera-import.sh`

**Files:**
- Create: `ops/kubera-import.sh`
- Test: `tests/test_ops_import.py`

**Interfaces:**
- Consumes: `ops/lib.sh`; bundle layout contract from Task 2 (artifact names; vault tar rooted at `/data/vault`; manifest fields `row_counts`, `vault_file_count`, `kek_fingerprint`).
- Produces:
  - CLI: `ops/kubera-import.sh BUNDLE_DIR [--domain NEW_DOMAIN] [--dest REPO_DIR] [--skip-setup] [--keep-bundle] [--dry-run]`
  - Contract used by Task 4: refuses to mutate anything until `verify_bundle` passes and `ROOT_MASTER_REK`-style preconditions hold; on success deletes bundle unless `--keep-bundle`; exits non-zero with message on every failure path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ops_import.py`:

```python
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


def test_corrupt_checksum_aborts_before_docker(tmp_path):
    bundle = make_bundle(tmp_path)
    # First create valid checksums via lib, then tamper.
    subprocess.run(
        ["bash", "-c",
         f'source "{REPO_ROOT}/ops/lib.sh"; write_checksums "{bundle}"'],
        check=True, capture_output=True,
    )
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
    subprocess.run(
        ["bash", "-c",
         f'source "{REPO_ROOT}/ops/lib.sh"; write_checksums "{bundle}"'],
        check=True, capture_output=True,
    )
    r = run(bundle, args=["--domain", "audit.new.example", "--dry-run"])
    assert r.returncode == 0, r.stderr
    assert "DOMAIN=audit.new.example" in r.stdout
    # Ordering: setup before restore before full up before verify.
    out = r.stdout
    assert out.index("get.docker.com") < out.index("pg_restore")
    assert out.index("pg_restore") < out.index("docker compose up -d")
    assert out.index("readyz") < out.index("VERIFICATION")


def test_keep_bundle_flag_preserves_bundle_in_dry_run_plan(tmp_path):
    bundle = make_bundle(tmp_path)
    subprocess.run(
        ["bash", "-c",
         f'source "{REPO_ROOT}/ops/lib.sh"; write_checksums "{bundle}"'],
        check=True, capture_output=True,
    )
    r_keep = run(bundle, args=["--dry-run"])
    r_drop = run(bundle, args=["--dry-run", "--keep-bundle"])
    assert "rm -rf" in r_keep.stdout          # default cleans bundle
    assert "rm -rf" not in r_drop.stdout      # kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ops_import.py -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the implementation**

Create `ops/kubera-import.sh`:

```bash
#!/usr/bin/env bash
# Set up a fresh box from a Kubera bundle: Docker, repo placement, DB+vault
# restore, stack start, manifest verification.
# Usage: ops/kubera-import.sh BUNDLE_DIR [--domain D] [--dest DIR]
#                          [--skip-setup] [--keep-bundle] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

BUNDLE=""
NEW_DOMAIN=""
DEST="${KUBERA_DEST:-$HOME/kubera}"
SKIP_SETUP=0
KEEP_BUNDLE=0
DRY_RUN="${DRY_RUN:-0}"

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) NEW_DOMAIN="$2"; shift 2 ;;
    --dest) DEST="$2"; shift 2 ;;
    --skip-setup) SKIP_SETUP=1; shift ;;
    --keep-bundle) KEEP_BUNDLE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) die "unknown option: $1 (first arg must be BUNDLE_DIR)" ;;
  esac
done
[ -n "$BUNDLE" ] || die "usage: kubera-import.sh BUNDLE_DIR [options]"
[ -d "$BUNDLE" ] || die "bundle dir not found: $BUNDLE"

# ---------- Preconditions: verify BEFORE touching anything ----------
log "verifying bundle integrity..."
verify_bundle "$BUNDLE"
load_env "$BUNDLE/env"
[ -n "${ROOT_MASTER_KEK:-}" ] || die "bundle env has empty ROOT_MASTER_KEK — refusing"
log "kek fingerprint: $(kek_fingerprint)"

install_setup() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRYRUN: ensure Docker Engine + Compose v2 (get.docker.com installer if missing)"
    echo "DRYRUN: ensure git (apt-get install -y git if missing)"
    echo "DRYRUN: mkdir -p $DEST"
    return 0
  fi
  if ! docker compose version >/dev/null 2>&1; then
    log "installing Docker Engine + Compose v2 (official installer)..."
    need_cmd curl
    bash -c "curl -fsSL https://get.docker.com | sh"
  fi
  if ! command -v git >/dev/null 2>&1; then
    apt-get update && apt-get install -y git
  fi
  mkdir -p "$DEST"
}

restore_vault() {
  log "restoring vault files..."
  dr_run docker compose up -d postgres
  dr_run docker compose run --rm -T --entrypoint sh api \
    -c "mkdir -p /data/vault && tar xzf - -C /data/vault"
}

restore_db() {
  log "restoring database..."
  dr_run bash -c "docker compose up -d postgres"
  dr_run bash -c "until docker compose exec -T postgres pg_isready -U \"\$POSTGRES_USER\" >/dev/null 2>&1; do sleep 2; done"
  dr_run bash -c "cat '$BUNDLE/db.dump' | docker compose exec -T postgres pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --exit-on-error"
}

start_stack() {
  log "starting full stack..."
  dr_run docker compose up -d
}

wait_healthy() {
  log "waiting for healthchecks..."
  dr_run bash -c "for i in \$(seq 1 60); do docker compose ps --status running >/dev/null 2>&1 && break; sleep 5; done"
}

verify_against_manifest() {
  log "probing readiness..."
  dr_run bash -c "curl -fsS http://127.0.0.1:8000/readyz"
  if [ "$DRY_RUN" = "1" ]; then
    echo "VERIFICATION PASSED (dry-run: live manifest comparisons skipped)"
    return 0
  fi
  local fail=0 t expected actual
  for t in companies documents document_versions audit_engagements; do
    expected="$(json_field "$BUNDLE/manifest.json" "['row_counts'].get('$t', 0)")"
    actual="$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
      "SELECT count(*) FROM $t" || echo ERR)"
    if [ "$expected" = "$actual" ]; then
      log "  OK  $t=$actual"
    else
      warn "MISMATCH $t: manifest=$expected actual=$actual"
      fail=1
    fi
  done
  expected="$(json_field "$BUNDLE/manifest.json" "['vault_file_count']")"
  actual="$(docker run --rm alpine:3 sh -c \
    'find /data/vault -type f 2>/dev/null | wc -l' 2>/dev/null || echo ERR)"
  # vault lives in a named volume; query through compose network namespace of api
  actual="$(docker compose exec -T api sh -c 'find /data/vault -type f | wc -l' || echo ERR)"
  if [ "$expected" = "$actual" ]; then
    log "  OK  vault_files=$actual"
  else
    warn "MISMATCH vault_files: manifest=$expected actual=$actual"
    fail=1
  fi
  local mf_fp cur_fp
  mf_fp="$(json_field "$BUNDLE/manifest.json" "['kek_fingerprint']")"
  cur_fp="$(kek_fingerprint)"
  [ "$mf_fp" = "$cur_fp" ] || { warn "KEK fingerprint mismatch"; fail=1; }
  if [ "$fail" != "0" ]; then
    die "verification failed — inspect warnings above; old server untouched"
  fi
  echo "VERIFICATION PASSED"
}

# ---------- Execute ----------
if [ "$SKIP_SETUP" != "1" ]; then
  install_setup
fi

if [ "$DRY_RUN" != "1" ]; then
  [ -f "$DEST/docker-compose.yml" ] || die "no docker-compose.yml at $DEST — place the repo first (or pass --dest)"
  cd "$DEST"
  cp "$BUNDLE/env" .env
  chmod 600 .env
  if [ -n "$NEW_DOMAIN" ]; then
    apply_domain .env "$NEW_DOMAIN"
    log "DOMAIN set to $NEW_DOMAIN"
  fi
  load_env "$DEST/.env"
else
  log "DRYRUN: would install bundle env into $DEST/.env with DOMAIN=$NEW_DOMAIN"
  printf 'DRYRUN: cp env -> %s/.env (DOMAIN=%s)\n' "$DEST" "${NEW_DOMAIN:-<bundled>}"
fi

restore_vault
restore_db
start_stack
wait_healthy
verify_against_manifest

if [ "$KEEP_BUNDLE" = "1" ]; then
  log "bundle kept at $BUNDLE"
elif [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: rm -rf $BUNDLE   # default removes bundle (secrets + duplicate data)"
else
  log "cleaning bundle (contains secrets + duplicate data)"
  rm -rf "$BUNDLE"
fi

log "DONE. Next: point DNS at this server, then open https://<your-domain>/"
```

Make executable:

```bash
chmod +x ops/kubera-import.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ops_import.py -v`
Expected: PASS. (All dry-run paths print plan lines to stdout and execute nothing;
real-mode verification prints the final `VERIFICATION PASSED` marker.)

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -q`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add ops/kubera-import.sh tests/test_ops_import.py
git commit -m "feat(ops): import/restore script with preflight verification and manifest checks"
```

---

### Task 4: Orchestrator `ops/kubera-migrate.sh`

**Files:**
- Create: `ops/kubera-migrate.sh`
- Test: `tests/test_ops_migrate.py`

**Interfaces:**
- Consumes: `ops/kubera-export.sh` (last stdout line = bundle path), `ops/kubera-import.sh` (CLI from Task 3), `ops/lib.sh`.
- Produces:
  - CLI: `ops/kubera-migrate.sh USER@TARGET [--domain D] [--keep-live] [--keep-bundle] [--no-maintenance] [--dry-run]`
  - Behavior: export locally → stage throwaway ed25519 key on target → rsync bundle + repo tree to `~/kubera-staging/{bundle,repo}` → remote import → remove throwaway key on exit (success or failure) → print DNS/cutover checklist.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ops_migrate.py`:

```python
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
    assert out.index("authorized_keys") < out.index("sed -i.*kubera-migrate")
    # Transfer: bundle + repo tree with excludes, direct to staging dirs.
    assert "rsync" in out
    assert "--exclude .venv" in out
    assert "--exclude node_modules" in out
    assert "--exclude .git" in out
    assert "kubera-staging/bundle" in out
    assert "kubera-staging/repo" in out
    # Remote invocation carries domain + bundle path.
    assert "kubera-import.sh" in out
    assert "--domain new.example" in out
    # Cutover checklist printed.
    assert "DNS" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ops_migrate.py -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Write the implementation**

Create `ops/kubera-migrate.sh`:

```bash
#!/usr/bin/env bash
# End-to-end migration orchestrator: export here, ship to target over SSH,
# import there. Run ON THE SOURCE SERVER from the repo root.
# Usage: ops/kubera-migrate.sh USER@TARGET [--domain D] [--keep-live]
#                          [--keep-bundle] [--no-maintenance] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

TARGET=""
NEW_DOMAIN=""
KEEP_LIVE=()
KEEP_BUNDLE=()
NO_MAINT=()

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) NEW_DOMAIN="$2"; shift 2 ;;
    --keep-live) KEEP_LIVE=(--keep-live); shift ;;
    --keep-bundle) KEEP_BUNDLE=(--keep-bundle); shift ;;
    --no-maintenance) NO_MAINT=(--no-maintenance); shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*)
      if [ -z "$TARGET" ]; then
        die "usage: kubera-migrate.sh USER@TARGET [options]"
      fi
      ;;
    *)
      [ -z "$TARGET" ] || die "exactly one USER@TARGET expected"
      TARGET="$1"; shift ;;
  esac
done
[ -n "$TARGET" ] || die "usage: kubera-migrate.sh USER@TARGET [options]"
[[ "$TARGET" == *@* ]] || die "target must look like user@host"

require_repo
need_cmd rsync
need_cmd ssh-keygen
load_env "$PWD/.env"

DRY_RUN="${DRY_RUN:-0}"
STAGING="kubera-staging"
KEYDIR="$(mktemp -d)"
PRIVKEY="$KEYDIR/id_ed25519"
PUBCOMMENT="kubera-migrate-$(date +%Y%m%d-%H%M%S)"

cleanup() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRYRUN: ssh $TARGET \"sed -i '/$PUBCOMMENT/d' ~/.ssh/authorized_keys\"  # remove throwaway key"
  elif [ -f "$KEYDIR/key.pub" ]; then
    log "removing throwaway SSH key from target..."
    ssh -i "$PRIVKEY" -o IdentitiesOnly=yes "$TARGET" \
      "sed -i '/$PUBCOMMENT/d' ~/.ssh/authorized_keys" || \
      warn "could not remove throwaway key — remove '$PUBCOMMENT' from target authorized_keys manually"
  fi
  rm -rf "$KEYDIR"
}
trap cleanup EXIT

# 1) Export locally (kubera-export.sh prints the bundle path as its last line).
log "step 1/4: exporting bundle on source..."
if [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: $SCRIPT_DIR/kubera-export.sh ${KEEP_LIVE[*]:-} ${NO_MAINT[*]:-}"
  BUNDLE="$HOME/kubera-migration-dryrun"
else
  EXPORT_OUT="$("$SCRIPT_DIR/kubera-export.sh" ${KEEP_LIVE[@]+"${KEEP_LIVE[@]}"} ${NO_MAINT[@]+"${NO_MAINT[@]}"})"
  BUNDLE="$(printf '%s\n' "$EXPORT_OUT" | tail -n1)"
fi
log "bundle: $BUNDLE"

# 2) Stage throwaway key on target.
log "step 2/4: staging throwaway SSH key on $TARGET..."
if [ "$DRY_RUN" = "1" ]; then
  echo "DRYRUN: ssh-keygen -t ed25519 -N '' -C $PUBCOMMENT -f <tmpdir>/key"
  echo "DRYRUN: ssh $TARGET 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys' < <tmpdir>/key.pub"
else
  ssh-keygen -t ed25519 -N "" -C "$PUBCOMMENT" -f "$PRIVKEY" -q
  # Uses the operator's normal auth once (password/key); installs throwaway pubkey.
  ssh "$TARGET" \
    "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" \
    < "$KEYDIR/id_ed25519.pub"
fi

# 3) Ship bundle + repo tree.
log "step 3/4: transferring bundle + repo tree to $TARGET:$STAGING ..."
SSH_CMD="ssh -i $PRIVKEY -o IdentitiesOnly=yes"
dr_run ssh -i "$PRIVKEY" -o IdentitiesOnly=yes "$TARGET" \
  "mkdir -p ~/$STAGING/bundle ~/$STAGING/repo"
dr_run rsync -az --partial --checksum -e "$SSH_CMD" \
  "$BUNDLE/" "$TARGET:$STAGING/bundle/"
dr_run rsync -az --partial --checksum -e "$SSH_CMD" \
  --exclude .venv --exclude node_modules --exclude .git \
  --exclude __pycache__ --exclude .pytest_cache \
  --exclude celerybeat-schedule --exclude data \
  --exclude .maintenance.lock \
  ./ "$TARGET:$STAGING/repo/"

# 4) Remote import.
log "step 4/4: importing on $TARGET..."
IMPORT_CMD="./ops/kubera-import.sh ~/$STAGING/bundle --dest ~/$STAGING/repo"
[ -z "$NEW_DOMAIN" ] || IMPORT_CMD="$IMPORT_CMD --domain $NEW_DOMAIN"
[ "${#KEEP_BUNDLE[@]}" -eq 0 ] || IMPORT_CMD="$IMPORT_CMD --keep-bundle"
dr_run ssh -i "$PRIVKEY" -o IdentitiesOnly=yes "$TARGET" \
  "cd ~/$STAGING/repo && $IMPORT_CMD"

echo ""
echo "Migration complete. Cutover checklist:"
echo "  1. Confirm the verification report above (counts + readyz)."
if [ -n "$NEW_DOMAIN" ]; then
  echo "  2. Point DNS for $NEW_DOMAIN at the target's IP."
else
  echo "  2. Point the domain's DNS A record at the target's IP."
fi
echo "  3. Open https://<domain>/ and log in; open one tenant document."
echo "  4. Only after that: retire the old stack (docker compose down on source)."
```

Implementation notes:
- In dry-run, no local artifacts or network actions occur — every step is an echoed
  `DRYRUN:` line on stdout, including key generation/install/removal, so tests can
  assert the full lifecycle ordering (`ssh-keygen` → `authorized_keys` → `sed -i` removal).
- The key install in step 2 uses the operator's normal SSH auth once (to append the
  throwaway public key); all later connections use `-i $PRIVKEY -o IdentitiesOnly=yes`.
- `${KEEP_LIVE[@]+"${KEEP_LIVE[@]}"}` guards empty arrays under `set -u` on older bash.

Make executable:

```bash
chmod +x ops/kubera-migrate.sh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ops_migrate.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -q`
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add ops/kubera-migrate.sh tests/test_ops_migrate.py
git commit -m "feat(ops): end-to-end migration orchestrator over SSH"
```

---

### Task 5: Opt-in live-stack export smoke test

**Files:**
- Modify: `tests/test_ops_export.py` (append integration class)

**Interfaces:**
- Consumes: `ops/kubera-export.sh` real execution against the developer's running compose stack (`docker compose up -d postgres redis` minimum, plus a built `api` image for the vault-volume container).
- Produces: confidence that dump/tar/manifest/checksums work against real Docker; skipped silently in normal runs.

- [ ] **Step 1: Append the failing test**

Add to the bottom of `tests/test_ops_export.py`:

```python
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
        # NOTE: this leaves the dev stack's api/worker/beat STOPPED — restore:
        subprocess.run(["docker", "compose", "up", "-d", "api", "worker", "beat"],
                       cwd=REPO_ROOT, capture_output=True)
```

- [ ] **Step 2: Verify it is skipped by default and passes opt-in**

Run: `uv run pytest tests/test_ops_export.py -v`
Expected: 3 passed, 1 skipped (no Docker requirement).

Opt-in run (only with the local dev stack running):

```bash
docker compose up -d postgres redis api
KUBERA_OPS_ROUNDTRIP=1 uv run pytest tests/test_ops_export.py::TestLiveExportSmoke -v
```

Expected: PASS; afterwards `docker compose ps` shows api/worker/beat running again.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ops_export.py
git commit -m "test(ops): opt-in live-stack export smoke test"
```

---

### Task 6: Documentation — README migration & DR sections

**Files:**
- Modify: `README.md` (insert new top-level section after "Everyday operations")

**Interfaces:**
- Consumes: final CLIs of Tasks 2–4.
- Produces: operator-facing instructions; table-of-contents entry.

- [ ] **Step 1: Add TOC entry**

In the README table of contents, after the `6. [Everyday operations](#everyday-operations)` line, insert:

```markdown
6.5. [Server migration & disaster recovery](#server-migration--disaster-recovery)
```

(renumbering later entries is unnecessary if you use this decimal form; keep the existing numbering untouched.)

- [ ] **Step 2: Add the section body**

Insert after the "Everyday operations" section ends (before "Local development"):

````markdown
---

## Server migration & disaster recovery

All state (Postgres, encrypted vault files, secrets) lives in one **bundle** produced by
`ops/kubera-export.sh`. Migration and disaster recovery are the same operation:
*make a bundle, run the importer.*

### Migrate to a new server (one command, run on the OLD server)

```bash
./ops/kubera-migrate.sh ash@NEW-SERVER-IP --domain audit.example-new.com
```

What it does: maintenance mode → freeze writes → dump Postgres + archive vault +
copy `.env` (carries `ROOT_MASTER_KEK` — without it vault data is unreadable) →
verified transfer over SSH → installs Docker + repo on the bare target → restores,
starts the stack, verifies row/file counts against the manifest.

Then: point DNS at the new server, log in, open a tenant document, and only then
retire the old stack. Rollback before the DNS flip is trivial — the old server never
stopped serving anything you care about; just `docker compose up -d api worker beat &&
python3 maintenance.py off` to unfreeze it.

Useful flags: `--keep-live` (export without leaving the old stack frozen),
`--keep-bundle`, `--no-maintenance`, `--dry-run`.

Caddy provisions Let's Encrypt certificates automatically — just set `DOMAIN`,
point DNS, open ports 80/443. Never let two servers serve the same domain at once.

### Disaster recovery snapshot (any time)

```bash
./ops/kubera-export.sh                 # bundle in ~/kubera-migration-<ts>
./ops/kubera-export.sh --no-maintenance  # same, without the public countdown page
```

Freezes writes briefly (schedule in low-traffic windows). Copy the bundle anywhere safe;
it contains secrets — treat it accordingly (700/600 perms are set for you).

### Restore from a bundle (any machine with Docker)

Clone/copy the repo to the machine, then from the repo root:

```bash
./ops/kubera-import.sh /path/to/kubera-migration-<ts>           # bundled DOMAIN
./ops/kubera-import.sh /path/to/bundle --domain audit.example.com
```

The importer verifies checksums **before** touching anything and compares row counts,
vault file counts, and the KEK fingerprint against the manifest afterwards.

---
````

- [ ] **Step 3: Verify docs render sanely**

Run: `grep -n "Server migration" README.md | head`
Expected: TOC entry + heading found.

Manual skim: headings hierarchy consistent, fenced blocks closed.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: server migration & DR runbook in README"
```

---

## Completion checklist (operator rehearsal, outside CI)

These mirror the spec's Testing section and happen on real hardware, after Tasks 1–6:

1. Bare-box rehearsal on the actual target: run `./ops/kubera-migrate.sh user@target --domain <throwaway-domain>` from the production server during a quiet window; complete the printed checklist.
2. Roundtrip proof: on the new server, log in, open a tenant document (proves KEK carried correctly), create a test item, confirm it persists across `docker compose restart`.
3. DR drill (optional but recommended once): restore the migration bundle onto a third machine or the same server with wiped volumes; verify again.
