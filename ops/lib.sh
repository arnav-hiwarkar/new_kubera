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

# Parse a .env file WITHOUT sourcing it.
#
# `. .env` under `set -e` aborted every ops script the moment a value contained a
# space (SMTP_FROM_NAME=Kubera Compliance -> "Compliance: command not found",
# exit 127), which silently disabled backup, restore and migration. Sourcing is
# also a code-execution path: a password containing $(...) or backticks would run
# as a command.
#
# Semantics deliberately match Docker Compose's env_file parser, so the shell and
# the containers always agree on a value:
#   * blank lines and #-comments are skipped
#   * a leading `export ` is tolerated
#   * quoted values are taken literally
#   * unquoted values drop a trailing whitespace-preceded #comment
load_env() {
  local f="$1"
  [ -f "$f" ] || die ".env not found at $f"
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"          # strip leading whitespace
    case "$line" in ''|'#'*) continue ;; esac
    line="${line#export }"
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"             # strip trailing whitespace
    case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
      *)
        value="${value%%[[:space:]]#*}"
        value="${value%"${value##*[![:space:]]}"}"
        ;;
    esac
    export "$key=$value"
  done < "$f"
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
PYEOF
}

json_field() {
  local f="$1" expr="$2"
  case "$expr" in
    \[*) ;; # already subscript form, e.g. ['row_counts'].get('x', 0)
    *)
      local head rest
      head="${expr%%\[*}"
      rest="${expr#"$head"}"
      expr="['$head']$rest"
      ;;
  esac
  python3 -c 'import json,sys; print(eval("json.load(open(sys.argv[1]))" + sys.argv[2]))' "$f" "$expr" 2>/dev/null \
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
