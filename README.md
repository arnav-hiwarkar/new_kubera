# Kubera

Kubera is a comprehensive **multi-tenant** platform featuring DocVault, AuditEase, SecretarialEase, ROC Compliance, and an admin portal for managing company operations and compliance.

- **Backend:** FastAPI (async) · PostgreSQL · Redis · Celery
- **Frontend:** React + Vite · Tailwind CSS
- **Packaging:** [`uv`](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`)
- **Runtime:** Docker Compose (Postgres, Redis, API, Celery worker + beat, frontend, Caddy)

---

## Table of contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Configuration (`.env`)](#configuration-env)
4. [Deploy (server / production)](#deploy-server--production)
5. [Zero-downtime maintenance mode](#zero-downtime-maintenance-mode)
6. [Everyday operations](#everyday-operations)
6.5. [Server migration & disaster recovery](#server-migration--disaster-recovery)
7. [Local development (uv)](#local-development-uv)
8. [Database migrations](#database-migrations)
9. [Creating companies & users](#creating-companies--users)
10. [Operator scripts](#operator-scripts)
11. [Testing](#testing)
12. [API docs](#api-docs)
13. [Troubleshooting](#troubleshooting)

---

## Architecture

`docker compose` runs these services:

| Service    | What it is                                   | Port (host)      |
|------------|----------------------------------------------|------------------|
| `postgres` | PostgreSQL 16 database                       | `5433` → 5432    |
| `redis`    | Redis (cache, rate limits, Celery broker)    | `6379`           |
| `api`      | FastAPI app (runs migrations, then Uvicorn)  | `8000`           |
| `worker`   | Celery worker (background jobs, backups)     | —                |
| `beat`     | Celery beat (scheduled jobs, e.g. nightly backup) | —           |
| `frontend` | Built React app served by Nginx              | — (behind Caddy) |
| `gateway`  | Persistent app/maintenance traffic switch    | — (behind Caddy) |
| `caddy`    | Reverse proxy + automatic HTTPS              | `80`, `443`      |

Public traffic follows this path:

```text
Internet -> Caddy -> gateway -- app mode --------> frontend -> API
                           `-- maintenance mode -> standalone maintenance page
```

The gateway and its maintenance page do not depend on React, FastAPI, Postgres,
or Redis. Its selected mode and countdown state live in the persistent
`maintenance_runtime` Docker volume.

Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`. The Docker image installs them with `uv` at build time — **you do not need `uv` installed on a server to deploy.** `uv` is only needed for running the backend directly on your machine (see [Local development](#local-development-uv)).

---

## Prerequisites

### To deploy (any server)
Docker + Docker Compose v2 and Git. Install commands per distro:

**Ubuntu / Debian**
```bash
sudo apt update && sudo apt install -y git curl
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**CentOS / RHEL / Fedora**
```bash
sudo dnf install -y git curl
sudo dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

**Arch Linux**
```bash
sudo pacman -Syu
sudo pacman -S git docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

> After adding yourself to the `docker` group, **log out and back in** for it to take effect.

### To develop locally (macOS or Linux)
`uv` (for the backend) + Docker (for Postgres/Redis). Node.js 20+ only if you also work on the frontend.
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Configuration (`.env`)

Everything is configured through a single `.env` file at the repo root.

```bash
cp .env.example .env
```

Then set the secrets:

| Variable            | How to set it |
|---------------------|---------------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Your database credentials. |
| `JWT_SECRET_KEY`    | `openssl rand -hex 32` |
| `ROOT_MASTER_KEK`   | 32-byte hex (64 chars): `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `INTERNAL_API_KEY`  | A long random secret. **This is the root key** used to create companies/admins — keep it safe. |
| `DOMAIN`            | Your domain for production (Caddy will auto-provision HTTPS), or `localhost` for local use. |

### Host vs. container URLs (important)
The `DATABASE_URL`, `REDIS_URL`, and `CELERY_*` values in `.env` use **`localhost`** (Postgres on `5433`, Redis on `6379`). These are for running commands **directly on your machine** (outside Docker).

When you run the stack with `docker compose`, these are **automatically overridden** with the in-network service names (`postgres:5432`, `redis:6379`). So **the same `.env` works for both** — you don't change anything for deployment.

---

## Deploy (server / production)

```bash
# 1. Clone
git clone <your-repo-url> && cd new_kubera

# 2. Configure
cp .env.example .env
#    …edit .env: set POSTGRES_* , JWT_SECRET_KEY, ROOT_MASTER_KEK,
#    INTERNAL_API_KEY, and DOMAIN (your domain, or localhost)

# 3. Build and start everything
docker compose up -d --build
```

What happens:
- All images build (backend deps installed from `uv.lock`; frontend built with Vite).
- The `api` container **runs `alembic upgrade head` automatically** before serving — there is no separate migration step.
- Services come up in the background.

Once up:
- **App (via Caddy):** `http://<DOMAIN>` (or `https://<DOMAIN>` for a real domain — Caddy handles the certificate automatically).
- **API directly:** `http://localhost:8000` · Swagger at `/docs`.

Next: [create your first company & admin](#creating-companies--users).

### Upgrading an existing production installation to the maintenance gateway

An already-running Caddy process does **not** automatically reload when the
bind-mounted `Caddyfile` changes. During the first deployment of the gateway,
build the new service and gracefully load the new edge route:

```bash
git pull
docker compose up -d --build gateway

docker compose exec -T caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose exec -T caddy \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile

python3 maintenance.py status
```

The final status must show `Edge route: gateway:80`. Rebuilding only `api`,
`frontend`, `worker`, and `beat` intentionally keeps the public edge alive, so
it also cannot load a newly changed Caddyfile by itself. The maintenance `on`
and `off` commands now detect this condition, validate the mounted Caddyfile,
and safely reconcile live Caddy before continuing. `status` detects a mismatch
but remains read-only.

---

## Zero-downtime maintenance mode

Run the maintenance controls on the Docker host from the repository directory:

```bash
python3 maintenance.py on       # immediately route all public traffic to maintenance
python3 maintenance.py status   # show mode, countdown, config, and app readiness
python3 maintenance.py off      # verify readiness, count down 10 seconds, restore Kubera
```

`on` blocks every public route, including `/api/*`, while localhost and the
internal Docker network remain available for migrations and verification. The
maintenance page is standalone and continues working while the frontend, API,
worker, and beat containers are stopped or rebuilt.

Use this deployment sequence:

```bash
python3 maintenance.py on

docker compose up -d --build api frontend worker beat
docker compose exec api alembic upgrade head

python3 maintenance.py status
python3 maintenance.py off
```

The `off` command refuses to begin its countdown unless both the frontend and
API dependencies are ready. During the countdown, every open maintenance page
shows the same server-synchronized time and reloads automatically when Kubera
returns. Pressing Ctrl+C cancels the return and leaves maintenance enabled.

Modes reported by `status`:

- `app` — Kubera is serving normally.
- `maintenance` — the standalone maintenance page is serving all public routes.
- `closing` — the 10-second return countdown is active.

In addition to the mode, require both `Gateway: valid` and
`Edge route: gateway:80`. An edge route of `frontend:80` means the running
Caddy process is bypassing maintenance; `on` or `off` will repair it only after
validating that the mounted configuration targets the gateway.

You can verify the public response during maintenance:

```bash
curl -i https://<DOMAIN>/
curl -i https://<DOMAIN>/api/v1/auth/company/me
```

Both return the maintenance response with HTTP `503`, `Retry-After`, `no-store`,
and `noindex` headers. The direct API development port is bound to
`127.0.0.1:8000`, so it cannot bypass maintenance through the server's public IP.

> **Do not run `docker compose down` during a no-downtime maintenance window.**
> It removes Caddy and the gateway, which are the public edge. Rebuild only the
> application services shown above. Host, Docker daemon, network, DNS, and Caddy
> outages are outside the application-level zero-downtime guarantee.

If a switch reports a validation or reload failure, the script restores or
retains maintenance routing. Fix the reported gateway/configuration problem,
check `docker compose logs gateway caddy`, run `python3 maintenance.py status`, and
then rerun the desired command. Repeated `on`, `off`, and `status` commands are
safe.

Edge diagnostics:

```bash
# Desired configuration currently mounted in the container
docker compose exec -T caddy \
  caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile --pretty

# Configuration Caddy is actually serving from memory
docker compose exec -T caddy \
  wget -qO- http://127.0.0.1:2019/config/

# Relevant edge logs
docker compose logs --tail=100 caddy gateway
```

---

## Everyday operations

```bash
docker compose up -d              # start (reuses existing images)
docker compose up -d --build      # start AND rebuild images
docker compose down               # stop & remove containers (DB volume is kept)
docker compose ps                 # what's running
docker compose logs -f api        # follow API logs (migrations, startup, requests)
docker compose restart api        # restart one service
```

**When do I need `--build`?**
- **Changed dependencies (`pyproject.toml` / `uv.lock`) or the `Dockerfile`** → yes, `docker compose up -d --build`.
- **Changed backend Python code only** → no. The backend bind-mounts the source and runs with `--reload`, so changes are picked up live.
- **Changed frontend code** → yes, `--build` (the frontend is a compiled image).

So the common case — *"I just want to run the server"* — is simply:
```bash
docker compose up -d
```

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

**Requirements & notes for the target box:**
- SSH as **root**, or a sudo-capable user. The importer installs Docker via the
  official installer when missing; if it adds your user to the `docker` group you'll
  be asked to re-login (`newgrp docker`) and **re-run the importer — that is safe**
  (checksums are re-verified; the restore drops-and-recreates objects idempotently).
- Open ports **80 and 443** before starting, or Let's Encrypt issuance will fail.
- The bundle transfer resumes if interrupted (`rsync --partial --checksum`);
  every stage is safe to re-run.
- Redis state (sessions, rate-limit counters) is intentionally not migrated:
  users just log in again on the new server.

**Source safety:** the old server's data is never modified or deleted by any of
these scripts. If an export fails midway, the script prints the exact command to
unfreeze the old stack (`docker compose up -d api worker beat && python3 maintenance.py off`).

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

## Local development (uv)

Run the backend directly on your machine (fast iteration, debugging, tests), using Docker only for Postgres/Redis.

```bash
# 1. Install dependencies into .venv (exact locked versions, Python 3.12)
uv sync

# 2. Create .env (see Configuration). The default localhost URLs are correct for host dev.
cp .env.example .env    # then fill in the keys

# 3. Start just the infra you need
docker compose up -d postgres redis

# 4. Run things with `uv run` (no need to activate the venv)
uv run alembic upgrade head                                   # apply migrations
uv run uvicorn app.main:app --reload                          # run the API on :8000
uv run celery -A app.worker.celery_app worker --loglevel=info # background worker
uv run pytest                                                 # test suite
```

**Managing dependencies:**
```bash
uv add <package>                    # add a dependency
uv remove <package>                 # remove one
uv lock --upgrade-package <package> # bump a single locked version
uv sync                             # apply the lockfile to your .venv
```
Commit the updated `pyproject.toml` **and** `uv.lock` together.

---

## Database migrations

Migrations are managed with **Alembic** and read the DB URL from your settings (`DATABASE_URL`), so they hit the right database whether run on the host (`localhost:5433`) or inside Docker (`postgres:5432`).

- **On deploy:** run automatically by the `api` container (`alembic upgrade head`).
- **Locally / manually:**
  ```bash
  uv run alembic upgrade head                 # apply all pending migrations
  uv run alembic revision -m "describe change"# create a new (hand-edited) migration
  uv run alembic downgrade -1                 # roll back the last migration
  uv run alembic current                      # show the current revision
  ```
- **Inside a running stack:**
  ```bash
  docker compose exec api alembic upgrade head
  ```

---

## Creating companies & users

Kubera is multi-tenant — users cannot self-register companies. An operator creates a company + its admin using the `INTERNAL_API_KEY`; the admin then activates their account by setting a password.

### Option A — the helper script (recommended)
From the repo directory (needs `DOMAIN` + `INTERNAL_API_KEY` in `.env`):
```bash
python3 create_company.py
```
It prompts for the company name and admin email, then prints a **one-shot activation key** (shown once) and the activation URL.

### Option B — direct API call
```bash
curl -X POST http://localhost:8000/api/v1/auth/companies \
  -H "Content-Type: application/json" \
  -H "X-Internal-API-Key: <YOUR_INTERNAL_API_KEY>" \
  -d '{"name": "Acme Corp", "admin_email": "admin@acme.com"}'
```
Response (the `activation_key` is shown only once):
```json
{
  "company": { "id": "…", "name": "Acme Corp" },
  "admin":   { "id": "…", "email": "admin@acme.com", "role": "admin", "is_active": false },
  "activation_key": "…",
  "activation_expires_at": "…"
}
```

### Activation
The admin opens **`http://<DOMAIN>/activate`**, enters their **email + the activation key**, and sets their **password + full name** (valid for 48h). After that they log in at `/login`.

> Lost/expired key? Re-mint one with `POST /api/v1/auth/companies/{company_id}/reissue-key` (internal key required).

### More users
Once logged in, the admin adds employees/managers from the **Directory → Add User** in the app, controlling module access per user.

---

## Operator scripts

All scripts live at the repo root. There are two kinds:

**Scripts that talk to the database directly** (`import app`) — run them **inside the `api` container** on a server, or with **`uv run`** locally:

| Script | Purpose |
|--------|---------|
| `change_password.py <email>` | Reset the password of any company user **or** auditor. |
| `delete_user.py [email]`     | Soft-delete a user: disables login, frees their email for reuse, keeps their name on existing files. |
| `send_email.py`              | Send branded transactional/plain emails via SMTP or queue via Celery (interactive wizard or flags). |

```bash
# On a running server:
docker compose exec api python change_password.py user@acme.com
docker compose exec api python delete_user.py
docker compose exec api python send_email.py --verify

# Locally:
uv run change_password.py user@acme.com
uv run delete_user.py
uv run send_email.py
```

**Scripts that use the HTTP API / `psql`** (standard library only) — run on the host with `python3` from the repo directory (they read `.env` and use `curl` / `docker compose`):

| Script | Purpose |
|--------|---------|
| `create_company.py`  | Create a company + admin (prints the activation key). |
| `delete_company.py`  | **Permanently delete** a company: every user, document, file and audit record is destroyed, and the name + admin email are free to reuse from scratch. Irreversible. |
| `list_companies.py`  | List companies. |
| `list_users.py [filter]` | List users across companies (marks `DELETED` / `INACTIVE`). |
| `maintenance.py on\|off\|status` | Safely control the persistent public maintenance gateway. |

```bash
python3 create_company.py
python3 delete_company.py
python3 list_users.py acme
python3 maintenance.py status
```

> Other root `*.py` files (`e2e_*.py`, `debug_script.py`, `migrate.py`, `generate_docs.py`, …) are development/one-off utilities and are **not** needed for normal operation.

---

## Outbound Email & Custom Company SMTP

Kubera provides a unified email dispatch architecture supporting both platform-level defaults and per-company custom mail servers:

1. **System Default Email (`kubera@ethdc.in`)**:
   * Configured via `SMTP_*` variables in `.env` (STARTTLS on port 587 or direct SSL on port 465).
   * Used for system alerts, password recovery, and fallback communications.

2. **Per-Company Custom SMTP (Multi-Tenant)**:
   * Company Admins can configure their own organization's mail server under **Company Profile → Outbound Email & Custom SMTP**.
   * **Security**: Passwords are encrypted at rest with AES-256-GCM under the tenant's individual KEK (`CompanyKey`), preventing credential leaks.
   * **Live Diagnostics**: The UI includes a "Test Connection" button that validates handshake and latency against external SMTP servers before saving.
   * **Auditor Onboarding Invites**: When an auditor is invited to an audit engagement in AuditEase, Kubera automatically dispatches a branded invitation with smart routing (linking to `/auditor/register` for new auditors or `/auditor/login` for existing auditors) through the company's custom email, or falling back seamlessly to `kubera@ethdc.in`.
   * **Audit Trail**: Every email dispatched is logged in `email_logs` with delivery status, message IDs, latency, and error tracing.

---

## Testing

Tests use Postgres (a separate `kubera_test` database is created automatically) and Redis.

```bash
docker compose up -d postgres redis     # ensure infra is running
uv run pytest                            # run the whole suite
uv run pytest tests/test_auth.py -q      # a single file
uv run pytest -k "archive" -q            # by keyword
node --test maintenance/maintenance.test.js # maintenance countdown logic
```

---

## API docs

With the backend running:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## Troubleshooting

- **`docker: permission denied`** — you're not in the `docker` group yet; log out and back in (see [Prerequisites](#prerequisites)).
- **Scripts/host commands can't reach the DB (`could not translate host name "postgres"`)** — your `.env` still has container hostnames. For host commands use the `localhost` values from `.env.example` (`localhost:5433` for Postgres, `localhost:6379` for Redis). Compose overrides these for the containers, so this doesn't affect deployment.
- **Config validation error about missing `DATABASE_URL` / `JWT_SECRET_KEY` / …** — those required keys aren't set in `.env` (or you're running outside the repo dir, so `.env` isn't found).
- **Port already in use (`5433`, `6379`, `8000`, `80`)** — another process/stack is using it; stop it or change the mapping in `docker-compose.yml`.
- **Changed dependencies but they're not picked up** — rebuild: `docker compose up -d --build` (containers) or `uv sync` (local).
- **Migrations didn't run** — check `docker compose logs api` for the `alembic upgrade head` output; run it manually with `docker compose exec api alembic upgrade head`.
- On localhost: keep API_BASE_URL= to http://localhost:8000 and on deployed servers keep it unset
