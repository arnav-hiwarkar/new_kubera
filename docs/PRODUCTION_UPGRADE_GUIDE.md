# Kubera Production Upgrade & Operations Safety Guide

This guide details the exact, tested procedures for upgrading Kubera on a production server, how to safely stop or pause services without losing data, and the critical anti-patterns ("What NOT to do") that can cause catastrophic data loss or downtime.

---

## 1. Golden Rules & What NEVER To Do

### 1.1 NEVER run `docker compose down -v` or `docker volume prune`
* **Why it's fatal:** Kubera stores all persistent tenant data inside named Docker volumes:
  - `pgdata`: All relational data (users, companies, audit engagements, metadata, encrypted keys).
  - `vault_data`: Every encrypted document uploaded to Document Vault (`/data/vault`).
  - `backup_data`: The automated nightly backup archives (`/data/backups`).
  - `maintenance_runtime`: Edge maintenance mode state.
* The `-v` (or `--volumes`) flag tells Docker to **permanently delete all attached volumes**. Running `docker compose down -v` or `docker volume prune` immediately wipes your database and tenant documents.
* **What to do instead:** Use `docker compose stop` or `docker compose restart`.

### 1.2 NEVER run `docker compose down` (even without `-v`) as a normal restart
* **Why it hurts:** `docker compose down` terminates and destroys the network and container interfaces for **all** services, including `caddy` and `gateway`.
* When `gateway` and `caddy` are down, your public edge is completely offline. Any visitors will see a browser connection error (`ERR_CONNECTION_REFUSED`) instead of the friendly maintenance page.
* **What to do instead:** 
  - To stop the application while leaving the public maintenance page online:
    ```bash
    python3 maintenance.py on
    docker compose stop api worker beat
    ```
  - To stop individual containers: `docker compose stop <service>`.

### 1.3 NEVER rely on `alembic downgrade` in production
* **Why it fails:** 
  - Several migrations in Kubera have no-op `downgrade()` functions (`pass`).
  - Other migrations (e.g. `7e5ea3f3eed7_requirements_open_closed.py`) are explicitly documented as **"LOSSY BY DESIGN"**—downgrading permanently drops columns and loses data.
  - The `api` container runs `alembic upgrade head` on startup every time.
* **What to do instead:** Always take a database dump before deploying. If a deployment fails, the rollback path is to restore the database dump via `pg_restore`.

### 1.4 NEVER lose or regenerate `ROOT_MASTER_KEK` in `.env`
* **Why it's fatal:** Document Vault uses envelope encryption:
  $$\text{ROOT\_MASTER\_KEK} \longrightarrow \text{Company KEK} \longrightarrow \text{Document DEK} \longrightarrow \text{Ciphertext}$$
* If `ROOT_MASTER_KEK` is changed, lost, or overwritten without running the key rotation script (`ops/kubera-rotate-root-kek.py`), **every document across all tenants is permanently undecryptable**.
* Keep a secure, off-host copy of your production `.env` file (e.g., in a password manager or secrets vault).

### 1.5 NEVER put `docker-compose.override.yml` on a production server
* **Why it breaks security:** `docker-compose.override.yml` is strictly for local laptop development. It binds Postgres and Redis to `0.0.0.0` or `127.0.0.1` and mounts the local source tree, dismantling the hardened production network tier.
* `ops/kubera-verify-exposure.sh --local` will immediately fail if it detects this file on a server.

### 1.6 NEVER edit `POSTGRES_PASSWORD` in `.env` without `ALTER USER` first
* Changing `POSTGRES_PASSWORD` in `.env` does **not** change the password of an existing PostgreSQL database volume.
* If you change `.env` first, the database keeps the old password, and `api`/`worker`/`beat` will enter an infinite crash loop with `password authentication failed for user "kubera"`.

### 1.7 NEVER run `migrate.py`
* The file `migrate.py` at the repo root is an obsolete developer scratch script with hardcoded credentials. It must never be run. Use `alembic` via the `api` container.

---

## 2. How to Safely Stop, Pause, or Restart Services

### Overview of Service Persistence

| Service | Container Type | Storage / Persistence | Safe to Stop? |
|---|---|---|---|
| `postgres` | Stateful | `pgdata` volume | Yes. Stopping flushes buffers to disk cleanly. |
| `vault_data` (volume) | Storage | Named Docker volume | Retained across container recreations. |
| `redis` | In-memory cache & queue | **Ephemeral** (`--save ""`, no volume) | Safe to restart, but **in-flight Celery tasks or queued emails are lost**. |
| `api` | Stateless app | Connects to `postgres`, `redis`, `vault_data` | Yes. Safe to stop anytime. |
| `worker` / `beat` | Stateless workers | Connects to `redis`, `postgres`, `vault_data` | Yes. Safe to stop. |
| `gateway` | Edge proxy | `maintenance_runtime` volume | Keep running during maintenance to serve 503 page. |
| `caddy` | TLS terminator | `caddy_data`, `caddy_config` | Keep running to maintain SSL / certificates. |

---

### Scenario A: Pausing the App for Maintenance (Recommended)
When you need to pause incoming requests or do backend maintenance without taking down the website or dropping SSL:

```bash
# 1. Direct edge traffic to the maintenance page
python3 maintenance.py on

# 2. Stop application processing (Postgres, Caddy, and Gateway remain active)
docker compose stop api worker beat

# 3. Verify status
python3 maintenance.py status
```
* **Result:** Users visiting the site see the branded Maintenance screen. Caddy and SSL certificates remain active. All database and vault files remain safe in their volumes.

---

### Scenario B: Restarting a Single Service
If a single service needs a restart (e.g. worker stalled, or api config updated):

```bash
docker compose restart api
# or
docker compose restart worker
```

---

### Scenario C: Complete Server Shutdown (Host Reboot or Maintenance)
If you need to reboot the host operating system or shut down the entire stack without data loss:

```bash
# 1. Put the application in maintenance mode first
python3 maintenance.py on

# 2. Gracefully stop all containers
# Note: 'stop' terminates processes cleanly and leaves all volumes, networks, and configs intact
docker compose stop

# (Optional check: verify all containers are Exited cleanly)
docker compose ps
```

To start everything back up after reboot:
```bash
# 1. Bring up all containers
docker compose up -d

# 2. Verify all services are healthy
docker compose ps

# 3. Disable maintenance mode
python3 maintenance.py off
```

---

## 3. Step-by-Step Production Upgrade Procedure

Always execute major operations inside `tmux` or `screen` so an SSH disconnect does not leave commands half-finished.

```bash
tmux new -s upgrade
```

---

### Step 1: Create the Full Pre-Upgrade Backup Bundle
Before touching git or pulling any new code, take a full snapshot using Kubera's built-in export tool.

From the repository root (`/path/to/new_kubera`):

```bash
./ops/kubera-export.sh --keep-live
```

This runs automated consistency checks and creates a timestamped bundle in `$HOME/kubera-migration-<YYYYMMDD-HHMMSS>` containing:
- `db.dump` — Custom PostgreSQL binary dump (`pg_dump -Fc`)
- `vault.tar.gz` — Tarball of all files in `/data/vault`
- `env` — Exact copy of the current `.env` (permissions `600`)
- `manifest.json` — Commit SHA, row counts, vault file count, and KEK fingerprint
- `sha256sums.txt` — Cryptographic verification hashes

Verify the bundle exists and has non-zero sizes:
```bash
ls -lh ~/kubera-migration-*/
```

---

### Step 2: Tag the Current Code & Snapshot Config
Tag the exact working commit in Git and back up `.env`:

```bash
# Tag the current working commit
git tag "pre-upgrade-$(date +%Y%m%d-%H%M%S)"

# Backup .env locally
cp .env ".env.bak.$(date +%Y%m%d-%H%M%S)"
```

---

### Step 3: Enable Zero-Downtime Maintenance Mode
Route edge traffic to the standalone maintenance page served by the gateway:

```bash
python3 maintenance.py on
python3 maintenance.py status
```
*Expected status output:* `Edge route: gateway:80`, `Gateway: valid`.

---

### Step 4: Pull the Latest Changes
```bash
git pull origin main
```

---

### Step 5: Build and Start Updated Services
Rebuild the application images:

```bash
docker compose up -d --build api frontend worker beat
```

> [!IMPORTANT]
> **Did the git pull touch anything under `gateway/`?**
> (e.g. `gateway/nginx.conf`, `gateway/limits.conf`, or `gateway/Dockerfile`)
> If yes, you must also rebuild `gateway`:
> ```bash
> docker compose up -d --build api gateway frontend worker beat
> ```

---

### Step 6: Apply Database Migrations
Run Alembic migrations through the updated `api` container:

```bash
docker compose exec api alembic upgrade head
```

Verify that the current revision matches the migration head:
```bash
docker compose exec api alembic current
```

---

### Step 7: Post-Upgrade Verification Checklist
Run these quick health checks before turning maintenance off:

1. **Verify all services are healthy:**
   ```bash
   docker compose ps
   ```
   All services should display `Up` or `Up (healthy)`.

2. **Verify the API container is running as a non-root user:**
   ```bash
   docker compose exec api id
   # Must return: uid=10001(kubera) gid=10001(kubera)
   ```

3. **Check API and Gateway logs for warnings or errors:**
   ```bash
   docker compose logs api --tail 50
   docker compose logs gateway --tail 50
   ```

---

### Step 8: Disable Maintenance Mode
```bash
python3 maintenance.py off
```

`maintenance.py off` will:
1. Probe `http://frontend/index.html` and `http://api:8000/readyz` from *inside* the gateway container.
2. If both endpoints are responding properly, initiate a 10-second grace countdown.
3. Atomically switch edge routing back to live app traffic.

**Final Smoke Test:**
Open your browser, log in to the app, and open a document from Document Vault. Opening an encrypted document verifies that:
- The database schema is functional.
- The `api` container can read the `vault_data` volume.
- The `ROOT_MASTER_KEK` in `.env` successfully unwraps the company KEK and decrypts document contents.

---

## 4. Emergency Rollback Playbook

If the upgrade fails, database migrations break, or the app fails to start after `git pull`:

### Step 1: Put the stack into maintenance mode & stop writers
```bash
python3 maintenance.py on
docker compose stop api worker beat
docker compose up -d postgres
```

### Step 2: Restore the Pre-Upgrade Database Dump
Identify your backup bundle folder (e.g. `~/kubera-migration-20260902-173000`):

```bash
BUNDLE_DIR=$(ls -d ~/kubera-migration-* | tail -n 1)

cat "$BUNDLE_DIR/db.dump" | docker compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists --exit-on-error
```
*Note: `--clean --if-exists` drops tables created by new migrations and restores the original data.*

### Step 3: Restore the Vault (if any files were altered or deleted)
```bash
cat "$BUNDLE_DIR/vault.tar.gz" | docker compose run --rm -T --entrypoint sh api \
  -c "tar xzf - -C /data/vault"
```

### Step 4: Roll Back Code to Pre-Upgrade Tag
```bash
# Check your pre-upgrade tag from Step 2
PREV_TAG=$(git tag -l "pre-upgrade-*" | tail -n 1)
git checkout "$PREV_TAG"
```

### Step 5: Rebuild and Restart
```bash
docker compose up -d --build api frontend worker beat
docker compose ps
python3 maintenance.py off
```

---

## 5. Command Safety Matrix

| Command | Safety | Consequence / Note |
|---|---|---|
| `docker compose stop` | **SAFE** | Stops running containers. Preserves all data in volumes. |
| `docker compose restart <service>` | **SAFE** | Restarts specified container. Preserves all data. |
| `docker compose up -d --build` | **SAFE** | Rebuilds and replaces container images. Volume data is retained. |
| `python3 maintenance.py on / off` | **SAFE** | Atomic symlink switch at Nginx gateway. Zero data impact. |
| `./ops/kubera-export.sh --keep-live` | **SAFE** | Read-only dump of DB and vault without downtime. |
| `docker compose down` | **WARNING** | Drops the public edge (`caddy` & `gateway`). Site goes dark instead of showing maintenance page. |
| `alembic downgrade -1` | **DANGEROUS** | **Do not run in prod.** May be a no-op or permanently drop columns. Use DB restore instead. |
| `docker compose down -v` | **FATAL** | **NEVER RUN.** Permanently deletes `pgdata`, `vault_data`, and `backup_data`. |
| `docker volume prune` | **FATAL** | **NEVER RUN.** Deletes any unattached Docker volumes. |
