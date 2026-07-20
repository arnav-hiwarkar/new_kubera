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
5. [Everyday operations](#everyday-operations)
6. [Local development (uv)](#local-development-uv)
7. [Database migrations](#database-migrations)
8. [Creating companies & users](#creating-companies--users)
9. [Operator scripts](#operator-scripts)
10. [Testing](#testing)
11. [API docs](#api-docs)
12. [Troubleshooting](#troubleshooting)

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
| `caddy`    | Reverse proxy + automatic HTTPS              | `80`, `443`      |

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

```bash
# On a running server:
docker compose exec api python change_password.py user@acme.com
docker compose exec api python delete_user.py

# Locally:
uv run change_password.py user@acme.com
uv run delete_user.py
```

**Scripts that use the HTTP API / `psql`** (standard library only) — run on the host with `python3` from the repo directory (they read `.env` and use `curl` / `docker compose`):

| Script | Purpose |
|--------|---------|
| `create_company.py`  | Create a company + admin (prints the activation key). |
| `delete_company.py`  | **Archive** a company: disables all its logins, frees its name + admin email for reuse, retains encrypted data. |
| `list_companies.py`  | List companies. |
| `list_users.py [filter]` | List users across companies (marks `DELETED` / `INACTIVE`). |

```bash
python3 create_company.py
python3 delete_company.py
python3 list_users.py acme
```

> Other root `*.py` files (`e2e_*.py`, `debug_script.py`, `migrate.py`, `generate_docs.py`, …) are development/one-off utilities and are **not** needed for normal operation.

---

## Testing

Tests use Postgres (a separate `kubera_test` database is created automatically) and Redis.

```bash
docker compose up -d postgres redis     # ensure infra is running
uv run pytest                            # run the whole suite
uv run pytest tests/test_auth.py -q      # a single file
uv run pytest -k "archive" -q            # by keyword
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
