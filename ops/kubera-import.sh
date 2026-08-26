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
  dr_run bash -c 'until docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; do sleep 2; done'
  dr_run bash -c "cat '$BUNDLE/db.dump' | docker compose exec -T postgres pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --exit-on-error"
}

start_stack() {
  log "starting full stack..."
  dr_run docker compose up -d
}

wait_healthy() {
  log "waiting for healthchecks..."
  dr_run bash -c 'for i in $(seq 1 60); do sleep 5; docker compose ps --format "{{.Name}}" >/dev/null 2>&1 && break; done'
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
