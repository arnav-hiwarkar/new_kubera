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
DRY_RUN="${DRY_RUN:-0}"

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
