#!/usr/bin/env bash
# Lock a Kubera host down to SSH + HTTP + HTTPS, at both layers that matter.
#
# WHY TWO LAYERS
#
# Docker publishes a container port by writing a DNAT rule into the *nat* table's
# PREROUTING chain. iptables traverses nat/PREROUTING BEFORE the filter table's
# INPUT chain — which is where ufw and firewalld write their rules. So:
#
#     ufw deny 5433        <-- reports success, port stays open to the internet
#
# The only filter hook that sits in front of Docker's published ports is the
# DOCKER-USER chain, which Docker creates and never flushes, precisely so
# operators can put rules there. This script configures:
#
#   * DOCKER-USER  — inbound traffic to CONTAINERS  (the Docker blind spot)
#   * INPUT        — inbound traffic to HOST processes (sshd, and anything else
#                    someone installs later)
#
# Default policy on both: allow 22/80/443, drop everything else inbound from
# outside; container-to-container and established traffic keep working.
#
# SAFETY
#
#   * Dry run is the DEFAULT. Nothing is changed until you pass --apply.
#   * --ssh-port is REQUIRED, so an SSH lockout cannot happen by omission.
#   * Idempotent: rules are tagged with a comment and removed before re-adding,
#     so re-running does not stack duplicates.
#   * Run it inside `tmux`/`screen`, and keep your current SSH session open until
#     you have opened a SECOND session and confirmed it works.
#
# LIMITATIONS (read these)
#
#   * IPv4 only. If the Docker daemon has IPv6 + ip6tables enabled, a published
#     port could be reachable over IPv6 without traversing these rules. Kubera's
#     production compose publishes nothing except Caddy, so nothing is currently
#     exposed this way — but a future `ports:` entry would need ip6tables too.
#   * The container-traffic RETURN rules match RFC1918 source ranges. An attacker
#     able to spoof a private source address from the internet would bypass them.
#     Cloud providers and ISPs normally drop such packets (BCP38), but this script
#     cannot guarantee it. Use your provider's network firewall as well.
#
# Usage:
#     sudo ops/kubera-harden-firewall.sh --ssh-port 22              # dry run
#     sudo ops/kubera-harden-firewall.sh --ssh-port 22 --apply
#     sudo ops/kubera-harden-firewall.sh --ssh-port 22 --status
#     sudo ops/kubera-harden-firewall.sh --ssh-port 22 --revert --apply
#
# See docs/SECURITY_HARDENING.md.

set -euo pipefail

TAG="kubera-harden"
SSH_PORT=""
APPLY=0
REVERT=0
STATUS=0
EXTRA_TCP=()

log()  { printf '[kubera-harden] %s\n' "$*" >&2; }
warn() { printf '[kubera-harden] WARN: %s\n' "$*" >&2; }
die()  { printf '[kubera-harden] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,48p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ssh-port) SSH_PORT="${2:-}"; shift 2 ;;
    --allow-tcp) EXTRA_TCP+=("${2:-}"); shift 2 ;;
    --apply) APPLY=1; shift ;;
    --revert) REVERT=1; shift ;;
    --status) STATUS=1; shift ;;
    -h|--help) usage 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

[ "$(id -u)" -eq 0 ] || die "must run as root (use sudo)"
command -v iptables >/dev/null 2>&1 || die "iptables not found"

if [ "$STATUS" -eq 1 ]; then
  echo "=== filter/INPUT ==="
  iptables -L INPUT -n -v --line-numbers
  echo
  echo "=== filter/DOCKER-USER (governs published container ports) ==="
  iptables -L DOCKER-USER -n -v --line-numbers 2>/dev/null || echo "(chain absent — is Docker installed?)"
  echo
  echo "=== nat/PREROUTING (Docker's published-port DNAT rules) ==="
  iptables -t nat -L PREROUTING -n 2>/dev/null || true
  echo
  echo "=== listening sockets ==="
  ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null || true
  exit 0
fi

[ -n "$SSH_PORT" ] || die "--ssh-port is required (this script would otherwise be able to lock you out)"
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "--ssh-port must be a number, got: $SSH_PORT"

for port in ${EXTRA_TCP+"${EXTRA_TCP[@]}"}; do
  [[ "$port" =~ ^[0-9]+$ ]] || die "--allow-tcp must be a number, got: $port"
done

if ! iptables -L DOCKER-USER -n >/dev/null 2>&1; then
  warn "the DOCKER-USER chain does not exist — Docker may not be running."
  warn "Published container ports will NOT be filtered until it does. Start Docker,"
  warn "then re-run this script."
fi

# Sanity check: is sshd actually listening where we were told?
if command -v ss >/dev/null 2>&1; then
  if ! ss -ltn "( sport = :$SSH_PORT )" 2>/dev/null | grep -q ":$SSH_PORT"; then
    warn "nothing is listening on TCP $SSH_PORT — double-check --ssh-port before --apply"
  fi
fi

# ---------------------------------------------------------------------------
# Rule set
# ---------------------------------------------------------------------------
# Each entry is: <table> <chain> <rule spec>. Rules are appended in order, and
# every rule carries the $TAG comment so --revert can find exactly ours.

ALLOWED_TCP=("$SSH_PORT" 80 443)
ALLOWED_TCP+=(${EXTRA_TCP+"${EXTRA_TCP[@]}"})

build_rules() {
  RULES=()

  # --- DOCKER-USER: inbound to containers -----------------------------------
  # Return traffic for connections a container initiated.
  RULES+=("filter DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN")
  # Traffic that originates on the host or between containers on docker bridges.
  # `-i docker0 -o docker0` style pairs are too fragile with user-defined
  # networks (br-<hash> names), so match the private RFC1918 sources Docker uses.
  RULES+=("filter DOCKER-USER -s 172.16.0.0/12 -j RETURN")
  RULES+=("filter DOCKER-USER -s 10.0.0.0/8 -j RETURN")
  RULES+=("filter DOCKER-USER -s 192.168.0.0/16 -j RETURN")
  RULES+=("filter DOCKER-USER -i lo -j RETURN")
  # The public entry point.
  for port in "${ALLOWED_TCP[@]}"; do
    RULES+=("filter DOCKER-USER -p tcp --dport $port -j RETURN")
  done
  # Anything else aimed at a published container port: drop.
  RULES+=("filter DOCKER-USER -j DROP")

  # --- INPUT: inbound to host processes -------------------------------------
  RULES+=("filter INPUT -i lo -j ACCEPT")
  RULES+=("filter INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")
  RULES+=("filter INPUT -p icmp --icmp-type echo-request -m limit --limit 5/second -j ACCEPT")
  for port in "${ALLOWED_TCP[@]}"; do
    RULES+=("filter INPUT -p tcp --dport $port -m conntrack --ctstate NEW -j ACCEPT")
  done
  RULES+=("filter INPUT -j DROP")
}

build_rules

# ---------------------------------------------------------------------------
# Show the plan
# ---------------------------------------------------------------------------

if [ "$REVERT" -eq 1 ]; then
  log "REVERT: every rule tagged '$TAG' will be deleted from INPUT and DOCKER-USER."
  log "This leaves the host with NO inbound filtering. Only do this to recover access."
else
  log "Plan — allowed inbound TCP: ${ALLOWED_TCP[*]}"
  echo
  for rule in "${RULES[@]}"; do
    read -r table chain spec <<<"$rule"
    printf '  iptables -t %s -A %s %s -m comment --comment %s\n' \
      "$table" "$chain" "$spec" "$TAG"
  done
  echo
fi

if [ "$APPLY" -eq 0 ]; then
  log "DRY RUN — nothing changed. Re-run with --apply to install these rules."
  log "Review the plan above carefully; confirm TCP $SSH_PORT is your real SSH port."
  exit 0
fi

# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

# Remove any rules we installed previously, so re-running is idempotent and so
# --revert has something precise to undo. Deleting by rule number from the bottom
# avoids renumbering surprises.
purge_tagged() {
  local chain="$1"
  iptables -L "$chain" -n --line-numbers 2>/dev/null \
    | awk -v tag="$TAG" '$0 ~ tag {print $1}' \
    | sort -rn \
    | while read -r n; do iptables -D "$chain" "$n"; done
}

log "removing previously installed '$TAG' rules (if any)"
purge_tagged INPUT
purge_tagged DOCKER-USER || true

if [ "$REVERT" -eq 1 ]; then
  log "reverted. The host is now unfiltered — re-run without --revert to protect it."
  exit 0
fi

for rule in "${RULES[@]}"; do
  read -r table chain spec <<<"$rule"
  # shellcheck disable=SC2086
  iptables -t "$table" -A "$chain" $spec -m comment --comment "$TAG"
done

log "rules installed."

# ---------------------------------------------------------------------------
# Persist across reboot — the step people forget
# ---------------------------------------------------------------------------

persist() {
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save && { log "persisted via netfilter-persistent"; return 0; }
  fi
  if command -v iptables-save >/dev/null 2>&1; then
    for target in /etc/iptables/rules.v4 /etc/sysconfig/iptables; do
      if [ -d "$(dirname "$target")" ]; then
        iptables-save > "$target" && { log "persisted to $target"; return 0; }
      fi
    done
  fi
  return 1
}

if ! persist; then
  warn "COULD NOT PERSIST THE RULES — they will vanish on reboot."
  warn "On Debian/Ubuntu:  apt install -y iptables-persistent && netfilter-persistent save"
  warn "On RHEL/CentOS:    yum install -y iptables-services && service iptables save"
fi

cat >&2 <<EOF

[kubera-harden] DONE. Verify before you disconnect:

  1. Open a SECOND SSH session now, while this one is still connected.
  2. Confirm exposure from OUTSIDE the box:
       ops/kubera-verify-exposure.sh --remote <this-server-ip>
     Expect 80 and 443 open, 5433 / 6379 / 8000 closed.
  3. Confirm the app still works: curl -I https://<your-domain>/
  4. If you locked yourself out, use the provider's serial/rescue console and run:
       sudo ops/kubera-harden-firewall.sh --ssh-port $SSH_PORT --revert --apply
EOF
