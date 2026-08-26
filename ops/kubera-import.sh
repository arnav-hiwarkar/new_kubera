#!/usr/bin/env bash
# Set up a box from a Kubera bundle: Docker, repo placement, DB+vault restore,
# stack start, manifest verification. Also the disaster-recovery restore path.
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
    --*) die "unknown option: $1" ;;
    *)
      [ -z "$BUNDLE" ] || die "exactly one BUNDLE_DIR expected"
      BUNDLE="$1"; shift ;;
  esac
done
[ -n "$BUNDLE" ] || die "usage: kubera-import.sh BUNDLE_DIR [options]"
[ -d "$BUNDLE" ] || die "bundle dir not found: $BUNDLE"
# Absolutize: we cd into DEST later, so a relative BUNDLE path would break.
BUNDLE="$(cd "$BUNDLE" && pwd)"

# ---------- Preconditions: verify BEFORE touching anything ----------
log "verifying bundle integrity..."
verify_bundle "$BUNDLE"
load_env "$BUNDLE/env"
[ -n "${ROOT_MASTER_KEK:-}" ] || die "bundle env has empty ROOT_MASTER_KEK — refusing"
log "kek fingerprint: $(kek_fingerprint)"

# Privilege helper: bare-box setup needs root; use sudo when run as a normal user.
PRIV=""
if [ "$(id -u)" != "0" ]; then
  need_cmd sudo
  PRIV="sudo"
fi

install_setup() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRYRUN: ensure Docker Engine + Compose v2 (get.docker.com installer if missing)"
    echo "DRYRUN: ensure git (apt-get install -y git if missing)"
    echo "DRYRUN: mkdir -p $DEST"
    return 0
  fi
  local docker_ok=0
  docker ps >/dev/null 2>&1 && docker_ok=1
  if [ "$docker_ok" != "1" ]; then
    log "installing Docker Engine + Compose v2 (official installer)..."
    need_cmd curl
    bash -c "curl -fsSL https://get.docker.com | $PRIV sh"
    # Allow the invoking user to drive docker without sudo on future runs.
    if [ "$(id -u)" != "0" ] && ! id -nG "$USER" | grep -qw docker; then
      $PRIV usermod -aG docker "$USER" || true
      warn "added '$USER' to the docker group — it activates on next login."
      warn "Run 'newgrp docker' OR log out/in, then RE-RUN this importer:"
      warn "  it is safe to re-run (checksums re-verified, restore is idempotent)."
      exit 3
    fi
    die "docker installed but not usable yet — re-run this importer"
  fi
  if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    $PRIV apt-get update && $PRIV apt-get install -y git curl
  fi
  mkdir -p "$DEST"
}

restore_vault() {
  log "restoring vault files..."
  dr_run bash -c "docker compose up -d postgres"
  dr_run bash -c "cat '$BUNDLE/vault.tar.gz' | docker compose run --rm -T --entrypoint sh api -c 'mkdir -p /data/vault && tar xzf - -C /data/vault'"
}

restore_db() {
  log "restoring database..."
  dr_run bash -c "docker compose up -d postgres"
  dr_run bash -c 'until docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; do sleep 2; done'
  # --clean --if-exists makes re-runs safe: objects are dropped before restore.
  dr_run bash -c "cat '$BUNDLE/db.dump' | docker compose exec -T postgres pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --clean --if-exists --exit-on-error"
}

start_stack() {
  log "starting full stack..."
  dr_run docker compose up -d
}

wait_healthy() {
  log "waiting for the API to become ready (first start builds images; up to ~10 min)..."
  if [ "$DRY_RUN" = "1" ]; then
    echo "DRYRUN: poll http://127.0.0.1:8000/readyz until HTTP 200 (timeout 600s)"
    return 0
  fi
  local i
  for i in $(seq 1 120); do
    if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=5)" >/dev/null 2>&1 || \
       (command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8000/readyz >/dev/null 2>&1); then
      log "API is ready."
      return 0
    fi
    sleep 5
  done
  die "API did not become ready within 600s — check: docker compose ps && docker compose logs api"
}

verify_against_manifest() {
  log "probing readiness..."
  dr_run bash -c "docker compose exec -T api python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000/readyz\", timeout=5)' 2>/dev/null || curl -fsS http://127.0.0.1:8000/readyz"
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
install_setup

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
  echo "DRYRUN: cp env -> $DEST/.env (DOMAIN=${NEW_DOMAIN:-<bundled>})"
fi

# Stop any older or conflicting containers holding ports
dr_run bash -c "docker stop \$(docker ps -q) 2>/dev/null || true"

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
