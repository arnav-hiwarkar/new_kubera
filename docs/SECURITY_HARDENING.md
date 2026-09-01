# Security hardening & network exposure

How Kubera's network surface is meant to look, what was wrong before, and exactly
what to do on a server that is already running.

- [1. The intended exposure](#1-the-intended-exposure)
- [2. What was wrong, and why it mattered](#2-what-was-wrong-and-why-it-mattered)
- [3. Why a firewall alone does not fix it](#3-why-a-firewall-alone-does-not-fix-it)
- [4. How the fix is structured](#4-how-the-fix-is-structured)
- [5. Runbook: upgrading a live production server](#5-runbook-upgrading-a-live-production-server)
- [6. Runbook: rotating a placeholder ROOT_MASTER_KEK](#6-runbook-rotating-a-placeholder-root_master_kek)
- [7. Local development setup](#7-local-development-setup)
- [8. Verifying exposure](#8-verifying-exposure)
- [9. Provider firewalls and other hosts on the box](#9-provider-firewalls-and-other-hosts-on-the-box)
- [10. Known limitations](#10-known-limitations)
- [11. Ongoing checklist](#11-ongoing-checklist)

---

## 1. The intended exposure

On a production server, exactly three ports answer from the internet: SSH, 80 and
443. Everything else is either bound to loopback or has no host port at all.

| Service       | Host port          | Bound to            | Reachable from the internet         |
|---------------|--------------------|---------------------|-------------------------------------|
| `caddy`       | `80`, `443`        | all interfaces      | **Yes — intentional.** The only public entry point. |
| `api`         | `127.0.0.1:8000`   | loopback only       | No                                  |
| `postgres`    | none               | `data` network only | No                                  |
| `redis`       | none               | `data` network only | No                                  |
| `gateway`     | none               | `edge` network only | No                                  |
| `frontend`    | none               | `edge` network only | No                                  |
| `worker`, `beat` | none            | `data` network only | No                                  |

Plus, at the host level: SSH on whatever port you use.

`unit_tests/test_compose_exposure.py` enforces this by parsing
`docker-compose.yml`. If someone adds a `ports:` entry to a non-`caddy` service
without binding it to `127.0.0.1`, the test suite fails.

---

## 2. What was wrong, and why it mattered

Before this change, `docker-compose.yml` published:

```yaml
postgres:
  ports: ["5433:5432"]     # 0.0.0.0 — the whole internet
redis:
  ports: ["6379:6379"]     # 0.0.0.0 — the whole internet, with NO password
```

A short form with no host IP means all interfaces. Both were reachable from
anywhere.

**Redis was the more serious of the two**, because it had no `requirepass` at all.
Anyone who could open a socket to port 6379 had complete read/write access, and in
this codebase Redis is load-bearing in two ways:

- **It is the Celery broker** (`app/worker.py`). An attacker could enqueue
  arbitrary registered tasks with arbitrary arguments, or `FLUSHALL` the queue and
  silently drop every pending job.
- **It is the login and activation rate-limit store** (`app/rate_limit.py`).
  Deleting those counters removes the throttle on credential stuffing against
  `/auth/login` — the exposed Redis port turned into an authentication bypass
  assist on the *intentionally* public port 443.

Additionally, `CONFIG SET dir` + `CONFIG SET dbfilename` + `SAVE` lets an
unauthenticated client write arbitrary files with the Redis process's
permissions, and the Redis container shared the `backup_data` volume with `api`
and `worker`.

Postgres on `5433` was protected by a password, but that password was whatever was
in `.env` — and if `.env` was copied from `.env.example` and not edited, it was
`kubera_secret`, which is public in this repository. It exposed the entire
multi-tenant database, including the wrapped per-company encryption keys.

The root cause was structural, not a typo: **one compose file served both local
development and production.** The published ports existed for the local workflow
of running pytest and Alembic on the host, and shipping that file to a server
carried the dev conveniences along with it — including `uvicorn --reload` and a
bind-mount of the host source tree over the image's baked-in code.

---

## 3. Why a firewall alone does not fix it

This is the part that catches people, so it is worth being precise.

Docker publishes a container port by inserting a **DNAT rule into the `nat`
table's `PREROUTING` chain**. `ufw` and `firewalld` write their rules into the
**`filter` table's `INPUT` chain**. Packet traversal order is:

```
        ┌──────────────────┐        ┌──────────────┐        ┌───────────────┐
wire -> │ nat/PREROUTING   │  -->   │ filter/      │  -->   │ filter/INPUT  │
        │ (Docker's DNAT)  │        │ FORWARD      │        │ (ufw lives    │
        │  rewrites dest   │        │ DOCKER-USER  │        │  here)        │
        └──────────────────┘        └──────────────┘        └───────────────┘
                 │                         │
                 └── packet is now aimed ──┘
                     at the container, so it
                     is FORWARDed, and never
                     reaches INPUT at all
```

Once DNAT has rewritten the destination to a container IP, the packet is
*forwarded*, not delivered locally — so it never traverses `INPUT`. Consequently:

```bash
sudo ufw deny 5433        # reports "Rule added". Port 5433 stays open. Really.
sudo ufw status           # shows the deny rule. Still open.
```

The one `filter`-table hook that sits in front of Docker's published ports is the
**`DOCKER-USER` chain**, which Docker creates on startup and never flushes,
specifically so operators can add rules there.

So a complete host lockdown needs *both*:

- `DOCKER-USER` — for traffic destined to containers.
- `INPUT` — for traffic destined to host processes (`sshd`, and anything anyone
  installs on the box later).

`ops/kubera-harden-firewall.sh` configures both.

---

## 4. How the fix is structured

### 4.1 Compose split

`docker-compose.yml` is now the **production** file, and it is safe by default:

- `postgres` and `redis` publish nothing.
- `api` publishes `127.0.0.1:8000:8000` only. Maintenance mode depends on this
  (public traffic cannot bypass the gateway through the server's public IP), and
  `ops/kubera-import.sh` probes `http://127.0.0.1:8000/readyz` as a readiness
  fallback.
- `api`, `worker` and `beat` run the code baked into the image by `COPY . .`. No
  `--reload`, no `.:/code` bind-mount.

Development conveniences live in **`docker-compose.override.yml`**, which is
gitignored. Compose loads it automatically when it exists, so:

- On your machine: `cp docker-compose.override.yml.example docker-compose.override.yml`
  once, then `docker compose up -d` behaves as it always did.
- On a server: the file does not exist, so `docker compose up -d` runs the
  hardened configuration. **The safe path is the default path** — you cannot
  forget a `-f` flag and accidentally expose a database.

> A server must never have `docker-compose.override.yml`.
> `ops/kubera-verify-exposure.sh --local` fails loudly if it finds one.

### 4.2 Network segmentation

Two networks replace the implicit default:

| Network | Members                                | Purpose |
|---------|----------------------------------------|---------|
| `edge`  | `caddy`, `gateway`, `frontend`, `api`  | Public request path |
| `data`  | `api`, `worker`, `beat`, `postgres`, `redis` | Database and broker |

`api` is the only service on both. A compromised `caddy` or `frontend` container
cannot open a socket to Postgres or Redis at all — previously every container
could.

`data` is deliberately **not** marked `internal: true`, because `worker` and
`beat` need outbound egress to deliver SMTP mail.

### 4.3 Redis authentication

Redis now starts with `--requirepass`, driven by a new required `REDIS_PASSWORD`
in `.env`. All three Redis URLs (`REDIS_URL`, `CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`) carry the credential.

This matters *even with the port closed*: without it, any container on the box —
or any foothold anywhere on the internal network — gets unauthenticated control of
the job queue and the rate limiter.

`docker-compose.yml` uses `${REDIS_PASSWORD:?...}`, so the stack refuses to start
if the variable is missing rather than quietly falling back to no authentication.

> **Not done deliberately:** `rename-command CONFIG ""`, which would close the
> `CONFIG SET dir` arbitrary-file-write path. Kombu's Redis transport calls
> `CONFIG GET maxmemory` when it connects, so renaming the command breaks Celery.
> `requirepass` plus no published port covers the same ground.

### 4.4 Startup rejection of placeholder secrets

`app/config.py` now refuses to start when a secret is still the value shipped in
`.env.example`. This is a different class of hole from the open ports and in some
ways a worse one, because the affected secrets are reachable through port 443,
which is *supposed* to be open — no firewall helps.

| Variable | Check |
|----------|-------|
| `JWT_SECRET_KEY` | not the placeholder; ≥ 32 characters. Anyone with this value can forge a token for any user. |
| `ROOT_MASTER_KEK` | exactly 64 hex characters; not all zeros. Protects every tenant's vault. |
| `INTERNAL_API_KEY` | not the placeholder; ≥ 32 characters. Grants company creation. |
| `DATABASE_URL` | has a password, and it is not `kubera_secret`. |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | each carries a non-placeholder password. |

Every problem is reported at once, with the command to generate a replacement, so
you fix them in one pass instead of one restart per error:

```
Refusing to start with an insecure configuration:
  - JWT_SECRET_KEY is the .env.example placeholder — generate one with: openssl rand -hex 32
  - ROOT_MASTER_KEK is the all-zero .env.example placeholder — generate one with: ...
  - REDIS_URL has no password. Redis requires authentication — set REDIS_PASSWORD in .env ...
```

`KUBERA_ALLOW_INSECURE_DEFAULTS=1` bypasses the check. It is set by the root
`conftest.py` for the test suite. **Never set it on a server** — doing so
reintroduces exactly the hole the check exists to prevent.

### 4.5 Host firewall

`ops/kubera-harden-firewall.sh` installs the `DOCKER-USER` and `INPUT` rules
described in §3, and persists them so a reboot does not silently reopen the box.
It is dry-run by default and requires an explicit `--ssh-port`.

### 4.6 Verification

- `ops/kubera-verify-exposure.sh --local` — run on the server. Checks Docker's
  bindings, host listeners, the `DOCKER-USER` chain, and the absence of a dev
  override file.
- `ops/kubera-verify-exposure.sh --remote <host>` — run from your laptop. Actually
  connects to each port. **This is the only mode that gives ground truth**, since
  it is the only one that crosses the firewall the way an attacker does. Exits
  non-zero if anything private answers.

---

## 5. Runbook: upgrading a live production server

Read this whole section before starting. Budget about 15 minutes, plus KEK
rotation if §6 applies.

### 5.0 Before you touch anything

```bash
cd /path/to/new_kubera

# Take a full backup. Everything below is reversible; this is your safety net.
./ops/kubera-export.sh

# Record what is currently exposed, so you can compare afterwards.
# Run this from your LAPTOP, not the server:
./ops/kubera-verify-exposure.sh --remote <server-ip>
```

**Assume the exposed Redis and Postgres were reached.** They were open to the
internet with, respectively, no password and possibly a public one. Treat the
following as compromised and plan to rotate them regardless of what the logs show:
the Postgres password, `JWT_SECRET_KEY` (rotating it logs everyone out — that is
the point), `INTERNAL_API_KEY`, and `ROOT_MASTER_KEK` if it was ever the all-zero
placeholder. §6 covers the KEK.

### 5.1 Enter maintenance mode

```bash
python3 maintenance.py on
python3 maintenance.py status      # confirm: Edge route: gateway:80
```

Public traffic now goes to the standalone maintenance page. The gateway does not
depend on the API, Postgres or Redis, so it keeps serving through everything below.

### 5.2 Pull the new configuration

```bash
git pull

# A server must not have this file. It should not exist, but check.
ls docker-compose.override.yml 2>/dev/null && \
  echo "DELETE THIS — it republishes Postgres and Redis"
```

### 5.3 Update `.env`

Generate the new Redis password and the replacement secrets:

```bash
# Keep a copy of the current file before editing.
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)

REDIS_PW=$(openssl rand -hex 32)
echo "REDIS_PASSWORD=$REDIS_PW" >> .env
```

Then edit `.env` and set:

| Variable | Value |
|----------|-------|
| `REDIS_PASSWORD` | the value just appended |
| `REDIS_URL` | `redis://:$REDIS_PW@redis:6379/0` |
| `CELERY_BROKER_URL` | `redis://:$REDIS_PW@redis:6379/0` |
| `CELERY_RESULT_BACKEND` | `redis://:$REDIS_PW@redis:6379/0` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` — rotating logs all users out |
| `INTERNAL_API_KEY` | `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | see the note below before changing this |
| `DATABASE_URL` | must match `POSTGRES_PASSWORD` |

Use hex values. A password containing `@`, `:`, `/` or `%` needs URL-escaping
inside the connection strings and will fail in confusing ways if you forget.

The values `docker-compose.yml` passes to the containers are overridden to the
in-network hostnames anyway, so the exact host in these URLs does not matter for
the containers — but keep them consistent so host-side tooling works.

> **Changing `POSTGRES_PASSWORD` on an existing volume.** The
> `POSTGRES_PASSWORD` environment variable only initialises a *new* data
> directory; it does not change the password of an existing database. To actually
> rotate it:
>
> ```bash
> docker compose up -d postgres
> docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
>   -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD 'new-password-here';"
> ```
>
> Then set the same value in `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env`.
> If you skip this, the database keeps its old password and the app fails to
> connect after you change `.env`. Postgres is no longer reachable from outside
> the `data` network, so rotating it is lower urgency than the Redis password —
> but do it, because it was internet-facing until now.

### 5.4 Rebuild and restart

```bash
docker compose up -d --build
```

This recreates everything: the two new networks, the authenticated Redis, and
`api`/`worker`/`beat` running baked-in code without the source bind-mount. The
rebuild is required — without it the containers would still be running the old
configuration.

If `.env` still has a placeholder secret, `api` will exit and its logs will list
exactly what to fix:

```bash
docker compose logs api --tail=40
```

Redis has no volume, so its queue was always ephemeral across restarts — nothing
is lost by recreating it.

### 5.5 Migrate and verify

```bash
docker compose exec api alembic upgrade head
docker compose ps                      # every service healthy
docker compose logs --tail=50 worker   # confirm the worker connected to Redis
python3 maintenance.py off
```

`maintenance.py off` verifies readiness and counts down 10 seconds before
restoring traffic.

Confirm the app itself:

```bash
curl -I https://<your-domain>/
```

Then log in through the UI and open a tenant document — that exercises the whole
KEK chain and is the check that matters most.

### 5.6 Lock down the host

Do this **inside `tmux` or `screen`**, and keep your current SSH session open
until you have confirmed a second one works.

```bash
# Dry run first — read the printed rules and confirm the SSH port is right.
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22

# Apply.
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --apply
```

Then, **without closing your current session**, open a second SSH connection. If
it works, you are fine. If you are locked out, use your provider's serial or
rescue console:

```bash
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --revert --apply
```

If SSH runs on a non-standard port, pass that port. If you need another port open
(a monitoring agent, for instance), add `--allow-tcp 9100`.

### 5.7 Confirm from outside

From your laptop, not the server:

```bash
./ops/kubera-verify-exposure.sh --remote <server-ip>
```

Expected:

```
  PORT     STATE      VERDICT
  22       open       ok — expected to be reachable
  80       open       ok — expected to be reachable
  443      open       ok — expected to be reachable
  5433     closed     ok — correctly unreachable
  6379     closed     ok — correctly unreachable
  8000     closed     ok — correctly unreachable
  2019     closed     ok — correctly unreachable
```

And on the server:

```bash
./ops/kubera-verify-exposure.sh --local
```

### 5.8 Rollback

Everything above is reversible before you delete `.env.bak.*`:

```bash
python3 maintenance.py on
git checkout <previous-commit> -- docker-compose.yml
cp .env.bak.<timestamp> .env
docker compose up -d --build
python3 maintenance.py off
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --revert --apply
```

The one thing that is *not* trivially reversible is a `ROOT_MASTER_KEK` rotation
(§6) — which is why it is a separate, backed-up, dry-run-first procedure.

---

## 6. Runbook: rotating a placeholder ROOT_MASTER_KEK

**Check first, on the server:**

```bash
grep '^ROOT_MASTER_KEK=' .env
```

If the value is 64 zeros, or any other value from `.env.example`, the key
protecting every tenant's document vault is public in this repository. It must be
rotated. If it is already a real random value, skip this section.

### What rotation actually costs

Not much, because of how the key hierarchy is built:

```
ROOT_MASTER_KEK  ──wraps──>  per-company KEK   (company_keys.encrypted_kek)
                 ──wraps──>  per-document DEK  (encrypted under the company KEK)
                 ──wraps──>  document ciphertext
```

The root key appears in exactly one link. Rotating it re-wraps **one row per
company** — documents, DEKs and the company KEKs themselves are never touched or
re-encrypted. A hundred companies is a hundred row updates.

`ops/kubera-rotate-root-kek.py` does this. It does not import `app`, precisely
because `app.config` refuses to load the insecure configuration you are here to
fix.

### Procedure

```bash
# 1. Back up. Non-negotiable.
./ops/kubera-export.sh

# 2. Generate the new key and KEEP IT SAFE, offline, separate from the database.
#    Losing it means losing the vault contents permanently.
NEW_KEK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
OLD_KEK=$(grep '^ROOT_MASTER_KEK=' .env | cut -d= -f2)
echo "NEW: $NEW_KEK"

# 3. Maintenance mode.
python3 maintenance.py on

# 4. Dry run — decrypts and re-wraps every company key in memory, writes nothing.
docker compose run --rm --no-deps --entrypoint python api \
  ops/kubera-rotate-root-kek.py --old-kek "$OLD_KEK" --new-kek "$NEW_KEK"

# 5. Apply.
docker compose run --rm --no-deps --entrypoint python api \
  ops/kubera-rotate-root-kek.py --old-kek "$OLD_KEK" --new-kek "$NEW_KEK" --apply

# 6. Put the NEW key in .env, then restart.
#    The app is broken between step 5 and step 7 — that is expected.
sed -i "s|^ROOT_MASTER_KEK=.*|ROOT_MASTER_KEK=$NEW_KEK|" .env
docker compose up -d api worker beat

# 7. VERIFY: log in and open a tenant document. This is the real test.
python3 maintenance.py off
```

Keep the old key until step 7 succeeds. If a company's KEK fails to decrypt under
`--old-kek`, the script writes nothing and tells you which company — that means
either the old key is wrong or companies were created under different root keys.

The script runs inside a single transaction, so a failure part-way leaves the
database untouched.

### If rotation is needed, so is this

A leaked root KEK means the vault contents should be considered exposed. Rotating
the key stops future access with the old key; it does not undo past access.
Depending on your obligations, exposure of tenant documents may be a reportable
incident. That is a decision for you, not for this document — but do make it
consciously rather than by omission.

---

## 7. Local development setup

One extra step compared with before:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
```

After that `docker compose up -d` works exactly as it used to: Postgres on
`127.0.0.1:5433`, Redis on `127.0.0.1:6379`, and `uvicorn --reload` with your
source tree mounted.

Note the override binds to `127.0.0.1`, not `0.0.0.0`, even locally. A laptop on
an untrusted network has no reason to serve its dev database to the room.

Your `.env` must satisfy the same validation as production, so generate real
secrets once:

```bash
python3 - <<'PY'
import secrets
print("REDIS_PASSWORD  =", secrets.token_hex(32))
print("JWT_SECRET_KEY  =", secrets.token_hex(32))
print("INTERNAL_API_KEY=", secrets.token_hex(32))
print("ROOT_MASTER_KEK =", secrets.token_hex(32))
PY
```

Put the Redis password into `REDIS_URL`, `CELERY_BROKER_URL` and
`CELERY_RESULT_BACKEND` as `redis://:<password>@localhost:6379/0`. Host-side
tooling (pytest, Alembic, the operator scripts) reads these, and Redis now
requires authentication in both environments.

> Changing `ROOT_MASTER_KEK` locally makes any *existing* local vault fixtures
> undecryptable, since they were sealed under the old value. For a dev database
> that is usually fine — recreate the fixtures. If you care about the local data,
> run the §6 rotation script against it instead.

### The local Postgres password snag

`POSTGRES_PASSWORD` only initialises a **new** data directory. If you already have
a `pgdata` volume created under the old `kubera_secret` password — which the
validator now rejects — changing `.env` alone leaves the database still expecting
the old password, and you get `password authentication failed for user "kubera"`.

Pick one:

```bash
# (a) Change the password in the existing database to match the new .env.
docker compose up -d postgres
docker compose exec -T postgres psql -U kubera -d postgres \
  -c "ALTER USER kubera WITH PASSWORD '<the POSTGRES_PASSWORD from .env>';"

# (b) Or start clean, discarding local data. Note this destroys the dev database
#     AND the local vault, so only do it if you do not need what is in there.
docker compose down -v
docker compose up -d postgres redis
```

Option (a) will not work if the old password itself is unknown; in that case use
(b), or connect as the container's superuser. On a **server**, use option (a) —
never `down -v`, which deletes `pgdata` and `vault_data`. The same caveat is
called out in §5.3.

The test suite sets `KUBERA_ALLOW_INSECURE_DEFAULTS=1` in the root `conftest.py`,
so `pytest` runs regardless of what your `.env` contains.

---

## 8. Verifying exposure

Two checks, and you want both — they catch different mistakes.

```bash
# On the server: configuration-level check.
./ops/kubera-verify-exposure.sh --local

# From your laptop: ground truth. Exits non-zero if anything private answers.
./ops/kubera-verify-exposure.sh --remote <server-ip>
```

`--local` catches a stray `docker-compose.override.yml`, a wildcard-bound
listener, and an unconfigured `DOCKER-USER` chain. `--remote` catches everything
`--local` misses, including a firewall that looks correct and isn't.

The static checks run with the test suite:

```bash
pytest unit_tests/test_compose_exposure.py unit_tests/test_config_secrets.py -q
```

---

## 9. Provider firewalls and other hosts on the box

Two things this repository cannot do for you.

**Use your provider's network firewall too.** AWS security groups, DigitalOcean
cloud firewalls, Hetzner firewalls and the like filter *before* traffic reaches
the host, so they are immune to the Docker/iptables ordering problem in §3. Allow
inbound `22`, `80`, `443` and nothing else. This is the single highest-value
control available, and it costs one form.

**Other containers and services on the same box.** Nothing here constrains
software outside this compose project. The `DOCKER-USER` rules installed in §5.6
default-drop inbound traffic to *all* containers on the host, not just Kubera's,
so an unrelated stack that publishes a port will stop being reachable from
outside — intended, but worth knowing before you run it on a shared machine. If
that box runs something else that needs a public port, add it with
`--allow-tcp <port>` so the intent is explicit and recorded.

---

## 10. Known limitations

Being explicit about where this stops, so nobody assumes coverage that is not
there.

1. **The firewall script is IPv4 only.** It writes `iptables` rules, not
   `ip6tables`. If the Docker daemon has IPv6 with `ip6tables` enabled, a
   published port could be reachable over IPv6 without traversing `DOCKER-USER`.
   Nothing is currently exposed this way, because the only services with a
   published port are Caddy (intentionally public) and the API (bound to the
   IPv4 loopback address specifically) — and Postgres/Redis publish no port at
   all, so Docker creates no DNAT rule of either address family for them. A
   future `ports:` entry would need ip6tables rules added.
2. **The `DOCKER-USER` container-traffic rules match RFC1918 source ranges.** An
   attacker able to spoof a private source address from the internet would pass
   them. Providers and ISPs normally drop such packets (BCP38), but the script
   cannot enforce that — which is one more reason to use the provider firewall in
   §9.
3. **Redis `CONFIG` is not renamed.** See §4.3 — it would break Celery. The
   arbitrary-file-write path it enables requires authenticating first, which now
   requires the password.
4. **`migrate.py` still hardcodes `kubera:kubera_secret@localhost:5433`.** It is a
   development one-off, listed in the README as not needed for normal operation,
   and it will now fail. Left alone deliberately rather than expanding scope.
5. **This configuration has not been exercised against a live Docker daemon.**
   Compose file parsing and rendering were verified with `docker compose config`
   for both the production and dev-override cases, and the validator and exposure
   invariants are covered by unit tests — but a full `docker compose up` with real
   Postgres, Redis and Celery traffic was not run. Do the first rollout on a
   staging box if you have one.

---

## 11. Ongoing checklist

Before every deployment:

- [ ] `pytest unit_tests -q` passes — this includes the exposure and secret checks.
- [ ] `docker-compose.override.yml` does not exist on the server.
- [ ] `KUBERA_ALLOW_INSECURE_DEFAULTS` is not set on the server.

Periodically:

- [ ] `./ops/kubera-verify-exposure.sh --remote <server-ip>` from off-box.
- [ ] `sudo ./ops/kubera-harden-firewall.sh --ssh-port <port> --status` — confirm
      the rules survived the last reboot.
- [ ] Rotate `JWT_SECRET_KEY` and `INTERNAL_API_KEY`. Both are cheap: the first
      logs users out, the second only affects operator scripts.
- [ ] Confirm `ROOT_MASTER_KEK` is backed up somewhere that is *not* the server
      and *not* the database backup. Losing it loses the vault.

If you ever add a `ports:` entry to `docker-compose.yml`, the test suite will
fail. That is the intended behaviour — put it in the dev override instead, or bind
it to `127.0.0.1` and update the test's expectations deliberately.
