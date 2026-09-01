#!/usr/bin/env bash
# Prove what a Kubera host actually exposes, rather than assuming.
#
# Two modes:
#
#   --local            Run ON the server. Reads Docker's port bindings and the
#                      host's listening sockets, and prints the expected table.
#                      Fast, no network access needed, catches misconfiguration.
#
#   --remote <host>    Run from ANOTHER machine (your laptop). Actually connects
#                      to each port. This is the only mode that gives you ground
#                      truth, because it is the only one that traverses the
#                      firewall the way an attacker does — a `ufw` rule that
#                      silently fails to block a Docker port looks fine locally.
#
# Usage:
#     ops/kubera-verify-exposure.sh --local
#     ops/kubera-verify-exposure.sh --remote app.kuberacompliance.com
#     ops/kubera-verify-exposure.sh --remote 203.0.113.10 --ports 22,80,443,5433,6379,8000
#
# Exit status: 0 if the exposure matches expectations, 1 if anything unexpected
# is reachable — so this is usable as a post-deploy gate in a script.
#
# See docs/SECURITY_HARDENING.md.

set -uo pipefail

MODE=""
TARGET=""
# Ports we care about: the two that should be open, the three that must not be,
# and SSH which is expected but worth showing.
PORTS="22,80,443,5433,6379,8000,2019"
TIMEOUT=4

# Ports that are allowed to answer from outside.
EXPECTED_OPEN="22 80 443"

log()  { printf '[verify-exposure] %s\n' "$*" >&2; }
die()  { printf '[verify-exposure] ERROR: %s\n' "$*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --local) MODE="local"; shift ;;
    --remote) MODE="remote"; TARGET="${2:-}"; shift 2 ;;
    --ports) PORTS="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$MODE" ] || die "specify --local or --remote <host>"

row() { printf '  %-8s %-10s %s\n' "$1" "$2" "$3"; }

# ---------------------------------------------------------------------------
# Local mode: what does this host bind?
# ---------------------------------------------------------------------------

verify_local() {
  command -v docker >/dev/null 2>&1 || die "docker not found"
  [ -f docker-compose.yml ] || die "run this from the repository root"

  local failures=0

  if [ -f docker-compose.override.yml ]; then
    log "!! docker-compose.override.yml EXISTS on this host."
    log "!! That file is for local development only and publishes Postgres/Redis."
    log "!! On a server, delete it and run: docker compose up -d"
    failures=1
  fi

  echo
  echo "Container port publishing (docker compose ps):"
  echo
  docker compose ps --format '  {{.Service}}\t{{.Ports}}' 2>/dev/null \
    || docker compose ps 2>/dev/null \
    || log "could not query compose (is the stack up?)"

  echo
  echo "Host listening sockets bound to a non-loopback address:"
  echo
  local wildcard
  wildcard="$(ss -ltnH 2>/dev/null | awk '{print $4}' \
    | grep -Ev '^(127\.0\.0\.1|\[::1\]|127\.0\.0\.53)' || true)"
  if [ -z "$wildcard" ]; then
    echo "  (none)"
  else
    printf '%s\n' "$wildcard" | sed 's/^/  /'
    # Anything not on an expected port is a finding.
    while read -r addr; do
      [ -n "$addr" ] || continue
      local port="${addr##*:}"
      case " $EXPECTED_OPEN " in
        *" $port "*) ;;
        *) log "unexpected non-loopback listener on port $port ($addr)"; failures=1 ;;
      esac
    done <<<"$wildcard"
  fi

  echo
  echo "DOCKER-USER firewall chain (governs published container ports):"
  echo
  if iptables -L DOCKER-USER -n 2>/dev/null | tail -n +3 | grep -q .; then
    iptables -L DOCKER-USER -n 2>/dev/null | sed 's/^/  /'
  else
    log "DOCKER-USER has no rules. Docker-published ports are NOT firewalled."
    log "Run: sudo ops/kubera-harden-firewall.sh --ssh-port <port> --apply"
    failures=1
  fi

  echo
  if [ "$failures" -eq 0 ]; then
    log "local checks passed. Now confirm from OUTSIDE the box:"
    log "  ops/kubera-verify-exposure.sh --remote <this-server-ip>"
  else
    log "local checks FAILED — see the messages above."
  fi
  return "$failures"
}

# ---------------------------------------------------------------------------
# Remote mode: what can the internet actually reach?
# ---------------------------------------------------------------------------

with_timeout() {
  # Portable timeout: neither GNU `timeout`/`gtimeout` nor a `nc` flag that
  # reliably bounds connect() can be assumed present. macOS ships neither
  # coreutils' `timeout` nor a `nc` whose `-w` covers the initial connection —
  # confirmed empirically: `nc -z -w 4` against a firewalled (packet-dropping)
  # host took ~75s (the OS TCP connect timeout), not 4s. This backgrounds the
  # probe, races it against a `sleep`, and kills whichever loses.
  local secs="$1"; shift
  "$@" &
  local work_pid=$!
  ( sleep "$secs"; kill -TERM "$work_pid" ) 2>/dev/null &
  local watcher_pid=$!
  local status
  if wait "$work_pid" 2>/dev/null; then status=0; else status=1; fi
  kill "$watcher_pid" 2>/dev/null
  wait "$watcher_pid" 2>/dev/null
  return "$status"
}

probe() {
  # Returns 0 if the TCP port accepts a connection.
  local host="$1" port="$2"
  if command -v nc >/dev/null 2>&1; then
    with_timeout "$TIMEOUT" nc -z "$host" "$port" >/dev/null 2>&1
  else
    with_timeout "$TIMEOUT" bash -c "exec 3<>/dev/tcp/$host/$port" >/dev/null 2>&1
  fi
}

verify_remote() {
  [ -n "$TARGET" ] || die "--remote needs a host or IP"

  local failures=0
  echo
  echo "Probing $TARGET (timeout ${TIMEOUT}s per port)"
  echo
  row "PORT" "STATE" "VERDICT"
  row "----" "-----" "-------"

  local IFS=','
  for port in $PORTS; do
    local state verdict
    if probe "$TARGET" "$port"; then
      state="open"
    else
      state="closed"
    fi
    unset IFS

    case " $EXPECTED_OPEN " in
      *" $port "*)
        if [ "$state" = "open" ]; then
          verdict="ok — expected to be reachable"
        else
          verdict="WARNING — expected open, is this the right host?"
        fi
        ;;
      *)
        if [ "$state" = "open" ]; then
          verdict="FAIL — must not be reachable from outside"
          failures=1
        else
          verdict="ok — correctly unreachable"
        fi
        ;;
    esac
    row "$port" "$state" "$verdict"
    IFS=','
  done
  unset IFS

  echo
  if [ "$failures" -eq 0 ]; then
    log "PASS — only ${EXPECTED_OPEN// /, } are reachable from here."
  else
    log "FAIL — something that should be private answered from outside the host."
    log "Remember: ufw/firewalld do NOT block Docker-published ports."
    log "Run on the server: sudo ops/kubera-harden-firewall.sh --ssh-port <port> --apply"
  fi
  return "$failures"
}

case "$MODE" in
  local)  verify_local ;;
  remote) verify_remote ;;
esac
