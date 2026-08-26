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

# Source-safety net: on ANY failed exit (except dry-run), tell the operator how
# to bring the OLD server back. The old data itself is never modified or deleted.
on_exit_hint() {
  rc=$?
  if [ "$rc" != "0" ] && [ "${DRY_RUN:-0}" != "1" ]; then
    warn "export FAILED (exit $rc). Old data is untouched; service may be frozen."
    warn "Unfreeze the old server now with:"
    warn "  cd $PWD && docker compose up -d api worker beat && python3 maintenance.py off"
    warn "Then fix the issue and re-run this script (it creates a fresh bundle)."
  fi
}
trap on_exit_hint EXIT

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

# Locate the api container (its volumes are read via --volumes-from).
# Accepts a STOPPED leftover container too (-a): e.g. after a prior aborted
# migration — we are about to stop it anyway. If it doesn't exist at all,
# bring it up once (first-boot case), then re-check.
API_CID="$(docker compose ps -aq api | head -n1)"
if [ -z "$API_CID" ]; then
  log "api container not found — starting it once to attach vault volume..."
  dr_run docker compose up -d api
  sleep 3
  API_CID="$(docker compose ps -aq api | head -n1)"
fi
[ -n "$API_CID" ] || die "no api container even after 'up -d api' — is docker-compose.yml intact?"
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
  cp "$PWD/.env" "$BUNDLE/env"
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
