#!/usr/bin/env bash
# Move an existing host-side vault into the `vault_data` Docker volume.
#
# WHY THIS EXISTS
#
# .env ships VAULT_STORAGE_PATH as a RELATIVE path (./data/vault). Inside a
# container that resolves against WORKDIR /code, so the application reads and
# writes /code/data/vault — not the vault_data volume mounted at /data/vault.
#
# That was survivable while docker-compose.yml bind-mounted `.:/code`, because
# /code/data/vault WAS the host directory. The hardened compose file removes that
# bind-mount from production (it existed only for uvicorn --reload), and
# docker-compose.yml now pins VAULT_STORAGE_PATH=/data/vault explicitly.
#
# Consequence for any server that ran the old configuration: the real documents
# are sitting in <repo>/data/vault on the host, and the freshly-mounted volume is
# empty. Without this migration the application starts cleanly and every existing
# document 404s on download, which looks exactly like data loss.
#
# This script is idempotent, copies rather than moves (the host copy is left
# untouched as a fallback), never overwrites a file already in the volume, and
# verifies the file count afterwards.
#
# Usage:
#     ops/kubera-migrate-vault-to-volume.sh              # dry run (default)
#     ops/kubera-migrate-vault-to-volume.sh --apply
#     ops/kubera-migrate-vault-to-volume.sh --apply --src /srv/kubera/data/vault
#
# See docs/SECURITY_HARDENING.md.

set -euo pipefail

# shellcheck source=ops/lib.sh
. "$(dirname "$0")/lib.sh"

APPLY=0
SRC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --src) SRC="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

require_repo
load_env "$PWD/.env"

# Where the OLD configuration actually wrote documents.
if [ -z "$SRC" ]; then
  raw="${VAULT_STORAGE_PATH:-./data/vault}"
  case "$raw" in
    /*) SRC="$raw" ;;               # already absolute — same path in and out
    *)  SRC="$PWD/${raw#./}" ;;     # relative: it resolved against the repo root
  esac
fi

log "host-side vault (source): $SRC"
log "target: the vault_data volume, mounted at /data/vault"

if [ ! -d "$SRC" ]; then
  log "no host-side vault at $SRC — nothing to migrate."
  log "If this server never ran the bind-mounted configuration, that is expected."
  exit 0
fi

src_count="$(find "$SRC" -type f | wc -l | tr -d ' ')"
vol_count="$(docker compose run --rm --no-deps --user root --entrypoint sh api \
  -c 'find /data/vault -type f 2>/dev/null | wc -l' 2>/dev/null | tr -d ' \r')"
vol_count="${vol_count:-0}"

log "files on host:   $src_count"
log "files in volume: $vol_count"

if [ "$src_count" -eq 0 ]; then
  log "host-side vault is empty — nothing to migrate."
  exit 0
fi

if [ "$APPLY" -eq 0 ]; then
  log "DRY RUN — would copy $src_count file(s) into the volume, skipping any that"
  log "          already exist there, then chown them to uid 10001 (kubera)."
  log "Re-run with --apply to perform the migration."
  exit 0
fi

log "copying (existing files in the volume are never overwritten) ..."
# `cp -a -n`: preserve everything, never clobber. Runs as root because the volume
# may still be root-owned from a pre-non-root deployment; the chown follows.
# --cap-add CHOWN/DAC_OVERRIDE: the `api` service has `cap_drop: [ALL]`, which
# `docker compose run --user root` does NOT override — root without CAP_CHOWN
# cannot chown, and without CAP_DAC_OVERRIDE cannot write into a directory owned
# by another uid, even as uid 0. Confirmed empirically: omitting these two flags
# fails with "Operation not permitted" on every file.
docker compose run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE \
  -v "$SRC:/migrate-src:ro" --entrypoint sh api \
  -c 'mkdir -p /data/vault && cp -a -n /migrate-src/. /data/vault/ && chown -R 10001:10001 /data/vault'

after="$(docker compose run --rm --no-deps --user root --entrypoint sh api \
  -c 'find /data/vault -type f 2>/dev/null | wc -l' | tr -d ' \r')"
log "files in volume after migration: $after"

if [ "$after" -lt "$src_count" ]; then
  die "volume holds $after file(s) but the host had $src_count — migration incomplete. \
The host copy at $SRC has NOT been touched; investigate before restarting the stack."
fi

cat >&2 <<MSG

[kubera-ops] Vault migration complete.

  Next:
    1. docker compose up -d --build
    2. Download a document through the UI to confirm decryption works.
    3. Only after that, archive the host copy:
         tar czf ~/kubera-vault-preupgrade.tar.gz -C "$(dirname "$SRC")" "$(basename "$SRC")"
       Keep it until you are confident. Do not delete it the same day.
MSG
