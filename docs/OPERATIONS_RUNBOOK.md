# Operations runbook — deploy, migrate, rotate, recover

This is the procedure-first companion to [README.md](../README.md) and
[SECURITY_HARDENING.md](SECURITY_HARDENING.md). Those explain *why* the system is
built the way it is; this document is *what to type*, in order, with the specific
failure modes of Kubera's own scripts called out inline — every command below was
read out of the actual script it invokes, not out of memory. Where a step is
destructive, irreversible, or has a known footgun, it is marked **⚠**.

If a procedure here ever disagrees with a script's own `--help`/header comment,
the script wins — this document can drift, the script cannot.

## Contents

1. [Ten do's and don'ts](#1-ten-dos-and-donts)
2. [The secrets, and what rotating each one costs](#2-the-secrets-and-what-rotating-each-one-costs)
3. [Deploying](#3-deploying)
4. [Database migrations (Alembic)](#4-database-migrations-alembic)
5. [Rotating keys and passwords](#5-rotating-keys-and-passwords)
6. [Backups](#6-backups)
7. [Restoring from a backup (disaster recovery)](#7-restoring-from-a-backup-disaster-recovery)
8. [Migrating to a new server](#8-migrating-to-a-new-server)
9. [One-time: moving an old server's vault into its volume](#9-one-time-moving-an-old-servers-vault-into-its-volume)
10. [Maintenance mode reference](#10-maintenance-mode-reference)
11. [Firewall and exposure verification](#11-firewall-and-exposure-verification)
12. [Pre-deploy and periodic checklists](#12-pre-deploy-and-periodic-checklists)
13. [Known gaps — do not assume these are covered](#13-known-gaps--do-not-assume-these-are-covered)

---

## 1. Ten do's and don'ts

1. **Do** run every multi-step procedure below inside `tmux` or `screen` on the
   server. Several steps (firewall apply, KEK rotation, migration) leave the
   system in an intermediate state if your SSH session drops mid-way.
2. **Do** take a backup (`./ops/kubera-export.sh --keep-live`) before *any*
   procedure in this document that writes to the database or the vault — deploys
   that add migrations, key rotation, and restores are all in that set.
3. **Don't** create `docker-compose.override.yml` on a server. It republishes
   Postgres and Redis to the host and bind-mounts the source tree, undoing the
   entire hardened network story in one file. `ops/kubera-verify-exposure.sh
   --local` fails outright if it finds one.
4. **Don't** run `docker compose down -v`, `docker volume prune`, or `docker
   compose down` (no `-v`, even) as a reflex "restart everything" — `down` (any
   form) removes Caddy and the gateway, which are the public edge; `-v` and
   `prune` **destroy `pgdata`, `vault_data`, and `backup_data`** (backups live on
   the same host, same failure domain — see [§6](#6-backups)). Use `docker
   compose restart <service>` or `docker compose up -d` instead.
5. **Do** treat `ROOT_MASTER_KEK` as the one secret that is not just "rotate and
   move on": losing both the old and new value after a rotation commits means
   permanent, unrecoverable loss of every tenant's documents. Back it up
   somewhere that is not this server and not this database.
6. **Don't** trust `alembic downgrade` in production. At least two migrations
   have a no-op `downgrade()` and one is documented in its own source as lossy
   by design. See [§4](#4-database-migrations-alembic).
7. **Do** remember `ops/kubera-import.sh` deletes its bundle by default
   (`rm -rf $BUNDLE`) and unconditionally overwrites the destination `.env` and
   runs `pg_restore --clean --if-exists` (drops existing objects first). Never
   point it at a server you don't intend to overwrite; always pass `--keep-bundle`
   unless the bundle is disposable.
8. **Don't** assume the nightly backup tarball and the migration-bundle vault
   tarball extract the same way — they don't (different `tar -C` root). Using
   the wrong one produces an application that starts cleanly with an empty vault,
   which looks exactly like data loss. See [§7](#7-restoring-from-a-backup-disaster-recovery).
9. **Do** rebuild `gateway`, not just `api`, when a change touches anything under
   `gateway/` — the documented day-to-day deploy sequence in [§3](#3-deploying)
   deliberately excludes `gateway` because it serves the maintenance page through
   routine deploys. See the KUB-003 case study in
   [security_checks_notes.md](security_checks_notes.md) for what shipping only
   half of a gateway change looks like in practice.
10. **Don't** generate secrets with anything other than `openssl rand -hex 32` /
    `python -c "import secrets; print(secrets.token_hex(32))"`. Values containing
    `@ : / %` need URL-escaping inside the `redis://…`/`postgresql://…` URLs and
    will fail in ways that look unrelated to the secret itself.

---

## 2. The secrets, and what rotating each one costs

Every secret below is validated at startup by `app/config.py`'s
`_reject_insecure_secrets` — the API refuses to boot if any of them is still a
`.env.example` placeholder. This is deliberate: these are reachable through port
443, so no firewall protects a forgotten placeholder. `KUBERA_ALLOW_INSECURE_DEFAULTS=1`
bypasses that check and **must never be set on a server** — it exists only so
`pytest` can run without real secrets (`conftest.py` sets it).

| Secret | Protects | Rotation cost | Procedure |
|---|---|---|---|
| `ROOT_MASTER_KEK` | The entire document vault (two-tier envelope: root KEK → per-company KEK → per-document DEK → ciphertext) | **Cheap, but not reversible once applied.** Only one row per company is re-wrapped; documents are never touched. The window between commit and restart is a full outage for document access. Losing both keys is permanent data loss. | [§5.1](#51-root_master_kek--the-vault-master-key) |
| `JWT_SECRET_KEY` | Signs every access + refresh token | **Hard cutover.** No key ID, no dual-key verification — every logged-in user and auditor gets 401 immediately and must log in again. No data loss. | [§5.2](#52-jwt_secret_key) |
| `INTERNAL_API_KEY` | Company creation, activation-key reissue, lead capture, operator CLIs | **Hard cutover**, and it isn't only read from `.env` — the owner portal's Leads page takes it as a manual paste-in in the browser, so anyone using that page needs the new value communicated out of band. | [§5.3](#53-internal_api_key) |
| `POSTGRES_PASSWORD` | Database auth | Only takes effect for a *new* data directory. Changing `.env` alone does nothing to an existing `pgdata` volume — you must `ALTER USER` first. Wrong order is the single most common post-deploy crash-loop. | [§5.4](#54-postgres_password) |
| `REDIS_PASSWORD` | Celery broker + rate-limit store auth | Redis has **zero persistence** (`--save ""`, no volume) — any queued Celery task (emails, scheduled notifications) still in flight when Redis restarts is silently lost. Rate-limit counters resetting is harmless. | [§5.5](#55-redis_password) |
| SMTP credentials | Outbound email (system default + per-company custom SMTP) | No app-wide blast radius — lowest-risk rotation. | [§5.6](#56-smtp-credentials) |

None of these except `ROOT_MASTER_KEK` has a dedicated rotation script. The
others are: edit `.env`, restart the affected containers, verify.

---

## 3. Deploying

### 3.1 First deploy on a fresh server

```bash
git clone <repo-url> && cd new_kubera
cp .env.example .env
# edit .env: POSTGRES_*, REDIS_PASSWORD (+ all three Redis URLs), JWT_SECRET_KEY,
# ROOT_MASTER_KEK, INTERNAL_API_KEY, DOMAIN. The API refuses to start on any
# placeholder value.

docker compose up -d --build     # builds and starts every service — nothing to
                                  # pick and choose, so gateway/api/frontend are
                                  # never out of sync on a fresh install

sudo ./ops/kubera-harden-firewall.sh --ssh-port 22          # dry run first
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --apply  # inside tmux/screen

./ops/kubera-verify-exposure.sh --remote <server-ip>        # from your laptop
```

No manual database step: the `api` container runs `alembic upgrade head`
automatically before `uvicorn` starts, every time it starts (`docker-compose.yml`
line 86). No manual `.env` additions are required beyond the six placeholders
above — every other setting (rate limits, backup retention, token lifetimes) has
a working default; see `.env.example` for the full, documented list of optional
overrides.

**Verify before moving on:**
```bash
docker compose ps                       # every service healthy
docker compose exec api id              # uid=10001(kubera) — confirms non-root
curl -sI https://<DOMAIN>/ | grep -iE 'x-frame|x-content-type|strict-transport'
```
Then create the first company (`python3 create_company.py`) and confirm you can
activate, log in, and open a document — that last step is the one check that
exercises the whole KEK chain end to end.

### 3.2 Routine update deploy (zero-downtime, existing server)

```bash
python3 maintenance.py on
python3 maintenance.py status            # confirm: Edge route: gateway:80

git pull
docker compose up -d --build api frontend worker beat
docker compose exec api alembic upgrade head

python3 maintenance.py status
python3 maintenance.py off
```

**⚠ If the change touches anything under `gateway/`** (nginx config, rate-limit
zones, the gateway `Dockerfile`) — not just `app/` or `frontend/` — add `gateway`
to the build line:

```bash
docker compose up -d --build api gateway frontend worker beat
```

`gateway` is deliberately left out of the default list because it is what
*serves the maintenance page itself*; routine app-only deploys leave it running
throughout. Rebuilding it recreates that container, so expect a few seconds where
even the maintenance page is briefly unreachable while the new one starts (Caddy
reconnects automatically once its healthcheck passes). Confirm the new config
took with `docker compose exec gateway nginx -t`, and check `docker compose logs
gateway` for anything an nginx `rate-limit`/`real_ip` misconfiguration would
produce (see the KUB-003 write-up in
[security_checks_notes.md](security_checks_notes.md) for a real example of what
silently shipping only the `api` half of a gateway change looked like — the edge
rate-limit zone shared one bucket across every visitor on the internet, because
nobody rebuilt `gateway`).

`off` will not begin its ten-second countdown unless it can reach
`http://frontend/index.html` and `http://api:8000/readyz` **from inside the
gateway container** — if either is down, `off` refuses and maintenance stays on
with no data at risk. There is no `--force` to override this.

### 3.3 What does *not* need `--build`

Per README's "Everyday operations": changed backend Python only, running
**locally** with the dev override, is picked up live by `uvicorn --reload` —
no rebuild. Everything running as a built image (any server, or local without the
override) needs `--build` for any code change. Changed dependencies
(`pyproject.toml`/`uv.lock`) or a `Dockerfile` always need `--build`, everywhere.

### 3.4 Rolling back a deploy

Config/code rollback is straightforward; **the database schema is the part that
is not**, because `api` runs `alembic upgrade head` on every start — you cannot
roll back the code to before a migration while the schema stays at that
migration's head. See [§4.3](#43-if-a-migration-goes-wrong).

```bash
python3 maintenance.py on
git checkout <previous-commit-or-tag> -- docker-compose.yml   # if it changed
cp .env.bak.<timestamp> .env                                  # if secrets changed
docker compose up -d --build
python3 maintenance.py off
```

If the deploy you're rolling back from added a migration, restore the pre-deploy
database dump instead of relying on `alembic downgrade` — see
[§4.3](#43-if-a-migration-goes-wrong) and [§7](#7-restoring-from-a-backup-disaster-recovery).

---

## 4. Database migrations (Alembic)

### 4.1 Normal path — nothing to do

Every `api` container start runs `alembic upgrade head` before `uvicorn`
(`docker-compose.yml:86`). A migration failure means `uvicorn` never starts;
under `restart: unless-stopped` that becomes a restart loop. Check
`docker compose logs api` — `alembic/env.py` has special-cased error messages for
the two most common causes (wrong Postgres password, wrong hostname), each with
the exact fix printed. Anything else (bad migration SQL) gets no such help —
read the raw traceback.

### 4.2 Manual migration commands

```bash
# Inside a running stack:
docker compose exec api alembic upgrade head
docker compose exec api alembic current          # show current revision
docker compose exec api alembic history           # list all revisions

# Locally (uv), against DATABASE_URL from your .env:
uv run alembic upgrade head
uv run alembic revision -m "describe change"       # new hand-edited migration
uv run alembic current
```

`migrate.py` at the repo root is **not** a migration runner — it's a dev one-off
with hardcoded credentials that duplicates one already-applied migration.
**Never run it.** It is explicitly deprecated in README and
`SECURITY_HARDENING.md` §10.

### 4.3 If a migration goes wrong

**There is no supported `alembic downgrade` path in production.** This is a real
gap, not an oversight to route around: of 41 revisions,
- two have a literal no-op `downgrade()` (`pass`) — downgrading past them does
  nothing, silently;
- `7e5ea3f3eed7_requirements_open_closed.py` says in its own docstring that its
  downgrade is **"LOSSY BY DESIGN"** — eleven dropped columns are gone for good
  and several status values become indistinguishable from each other;
- the current head (`ddf024af58cd`, per-company SMTP config + email logs) has a
  clean, correct downgrade, but it drops two tables and every row in them.

`downgrade` is a development tool for iterating on an unmerged migration, not a
production incident response. **The actual rollback path is:**

```bash
python3 maintenance.py on
docker compose stop api worker beat
docker compose up -d postgres
# restore the pre-deploy dump (see §7 for the pg_restore command) —
# you took one in step 2 of §3.2/§3.4, right? If not, see §13.
git checkout <pre-migration-commit> -- .        # roll code back to match
docker compose up -d --build api worker beat
python3 maintenance.py off
```

If you skipped the pre-deploy backup, you no longer have a clean rollback for
schema changes — this is exactly why [§1](#1-ten-dos-and-donts) rule 2 exists.

---

## 5. Rotating keys and passwords

Every procedure in this section assumes you are on the server, in the repo
directory, with a current `.env`.

### 5.1 `ROOT_MASTER_KEK` — the vault master key

**When required:** `grep '^ROOT_MASTER_KEK=' .env` — if it's 64 zeros (the
`.env.example` placeholder) or matches any other example value, the key
protecting every tenant's documents is public in this repository and must be
rotated. Otherwise, rotate only if you believe the key was exposed.

**Why it's cheap:** the encryption is layered — `ROOT_MASTER_KEK` wraps one
per-company KEK each; that in turn wraps per-document keys; those wrap the actual
ciphertext. Rotating the root key means re-wrapping **one row per company** in
`company_keys`. No document is ever re-encrypted.

```bash
# 1. Back up. Non-negotiable — this is a database write.
./ops/kubera-export.sh --keep-live

# 2. Generate the new key. Keep it somewhere that is NOT this server and NOT
#    the database backup — losing both old and new after step 5 commits means
#    permanent loss of every tenant's vault.
NEW_KEK=$(python3 -c "import secrets; print(secrets.token_hex(32))")
OLD_KEK=$(grep '^ROOT_MASTER_KEK=' .env | cut -d= -f2)

# 3. Maintenance mode — the app will be broken between step 5 and step 7.
python3 maintenance.py on

# 4. Dry run. Decrypts and re-wraps every company key IN MEMORY. Writes nothing.
docker compose run --rm --no-deps --entrypoint python api \
  ops/kubera-rotate-root-kek.py --old-kek "$OLD_KEK" --new-kek "$NEW_KEK"

# 5. Apply. Single DB transaction — a failure partway rolls back everything,
#    the database is left untouched either way.
docker compose run --rm --no-deps --entrypoint python api \
  ops/kubera-rotate-root-kek.py --old-kek "$OLD_KEK" --new-kek "$NEW_KEK" --apply

# 6. Only now does .env get the new key. The script never edits .env itself.
sed -i "s|^ROOT_MASTER_KEK=.*|ROOT_MASTER_KEK=$NEW_KEK|" .env
docker compose up -d api worker beat

# 7. VERIFY: log in, open a tenant document. This is the real test — it's the
#    only step that proves the new key actually decrypts what step 5 wrote.
python3 maintenance.py off
```

**⚠ If step 5 succeeds and step 6 is not done yet, do not panic and re-run step
5** with the same `--old-kek` — it will now fail (the database already holds
keys wrapped under `$NEW_KEK`). Go straight to step 6.

**⚠ Once step 5 has committed, `$OLD_KEK` is no longer useful for decrypting the
database** — but keep it anyway until step 7 passes, as your only way back if
step 6 is somehow wrong. Destroy it only after a real tenant document opens
successfully.

Rotating this key is a security event worth documenting even when precautionary:
a leaked root KEK means vault contents should be considered exposed regardless of
whether you have evidence of access, and this may be a reportable incident for
some tenants. Make that call consciously.

### 5.2 `JWT_SECRET_KEY`

Signs both access and refresh tokens (`app/auth.py`). There is no key ID and no
dual-key verification window — the moment the new key is live, every previously
issued token fails to decode and every user (company and auditor) is logged out.
No data is at risk; this is purely a session cutover.

```bash
NEW_JWT=$(openssl rand -hex 32)
sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$NEW_JWT|" .env
docker compose up -d api
```
`worker`/`beat` never check this key — no need to restart them. Warn users ahead
of a planned rotation; there's no way to stagger it.

### 5.3 `INTERNAL_API_KEY`

Guards `POST /api/v1/auth/companies`, `POST …/reissue-key`, `POST
/api/v1/leads/interest`'s operator-only paths, and every operator CLI
(`create_company.py`, `delete_company.py`, `list_companies.py`, `list_leads.py`).
Compared with `secrets.compare_digest` — constant-time, but still a single static
value with no rotation window.

```bash
NEW_KEY=$(openssl rand -hex 32)
sed -i "s|^INTERNAL_API_KEY=.*|INTERNAL_API_KEY=$NEW_KEY|" .env
docker compose up -d api
```
The operator CLIs re-read `.env` on every invocation, so they need nothing else.
**The one thing this doesn't cover:** if the owner portal's Leads page is used
with a manually pasted-in key value in the browser, whoever uses that page needs
the new value communicated to them directly — it is not read from `.env` client-side.

### 5.4 `POSTGRES_PASSWORD`

**The password in `.env` only takes effect when the `pgdata` volume is first
created.** Editing `.env` alone on an existing deployment does nothing — the
running Postgres still expects the old password, and `api`/`worker`/`beat` will
crash-loop with `password authentication failed for user "kubera"` because they
now hand it the new one.

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD 'the-new-password';"
```
Then, and only then, update `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env` to
match, and:
```bash
docker compose up -d api worker beat
```
**⚠ Never** "fix" a password mismatch with `docker compose down -v` — that
destroys the volume you were trying to preserve, along with `vault_data` and
`backup_data` if they're targeted too (they aren't part of `-v` unless you also
remove them explicitly, but `down -v` removes every volume `docker-compose.yml`
declares — check the target list before running it, or better, don't run it at all).

### 5.5 `REDIS_PASSWORD`

Redis backs both the Celery broker and the rate-limit store, and it runs with
**no persistence at all** — `--save ""` and no volume mount. A Redis restart
therefore doesn't lose data in the durable sense, but it does silently drop
anything currently queued: pending emails, scheduled Celery tasks, in-flight
task results. Rate-limit counters resetting is harmless.

```bash
NEW_REDIS_PW=$(openssl rand -hex 32)
# Update REDIS_PASSWORD and all three URLs that embed it — there is no variable
# expansion inside .env, the literal password must appear in each:
#   REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
docker compose up -d redis api worker beat
```
Prefer rotating during a low-traffic window if the task queue is likely to be
non-empty (e.g. avoid the moments right after a bulk import or bulk notification
send). There's no drain command — if it matters, check queue depth with a Celery
inspect command before restarting, or just accept the loss (emails can be
resent; nothing here is unrecoverable).

### 5.6 SMTP credentials

Lowest blast radius. Update the relevant `SMTP_*` values in `.env` for the
system default, or the per-company config in-app for a tenant's custom server —
those are stored encrypted in the database, not in `.env`, and don't need a
restart. For the system default:
```bash
docker compose up -d api worker
```
Verify with `docker compose exec api python send_email.py --verify` before
relying on it.

---

## 6. Backups

### 6.1 What runs automatically

Celery beat fires `app.worker.nightly_backup` at **02:00 UTC daily**
(`app/worker.py`, hardcoded `crontab(hour=2, minute=0)` — not configurable via
`.env`). It produces **two** artifacts per run, timestamped, in `/data/backups`
(the `backup_data` volume):

- `db_backup_<ts>.dump` — `pg_dump -Fc` (PostgreSQL **custom format**; restore
  with `pg_restore`, not `psql`).
- `vault_backup_<ts>.tar.gz` — `tar -czf … -C /data vault`, i.e. **the tarball
  has a top-level `vault/` directory.** This matters — see [§7](#7-restoring-from-a-backup-disaster-recovery).

The task **raises on failure** rather than logging and continuing — a failed
backup surfaces as a visible Celery task failure, not a quietly-empty directory.
Old artifacts older than `BACKUP_RETENTION_DAYS` (default 14; `0` disables
pruning) are deleted automatically; unrelated files in the directory are never
touched.

**`BACKUP_PATH` is pinned to `/data/backups` in `docker-compose.yml` for `api`,
`worker`, and `beat`** — changing it in `.env` has no effect inside Docker.

### 6.2 What this backup does *not* give you

- **Not encrypted at rest beyond what's already encrypted.** The dump contains
  plaintext company profiles (CIN/PAN/GSTIN), user emails and bcrypt hashes,
  trial balances, asset registers, activity logs, and the *wrapped* company KEKs
  (still protected — `ROOT_MASTER_KEK` is not in this backup). Document
  ciphertext in the vault tarball stays encrypted.
- **Not off-host.** `backup_data` is a local Docker volume on the same disk as
  `pgdata` and `vault_data`. If the host is lost, so is the backup. This is a
  second copy in the same failure domain, not disaster recovery — for that, use
  [§7/§8](#7-restoring-from-a-backup-disaster-recovery)'s bundle mechanism, which
  is designed to leave the server.
- **Not integrity-checked beyond "is the file non-empty."**
- **`ROOT_MASTER_KEK` is not included.** A nightly backup restored onto a fresh
  host without the original `.env` produces a working-looking app whose
  documents are permanently undecryptable.

### 6.3 Manual trigger and inspection

```bash
docker compose exec worker python -c \
  "from app.worker import nightly_backup; print(nightly_backup())"
# → {"status": "success", "db_bytes": N, "vault_bytes": N, "pruned": N, ...}

docker compose exec api sh -c 'ls -la /data/backups | tail'
```
Check the returned byte counts, not just presence — an empty or truncated dump
still "exists."

---

## 7. Restoring from a backup (disaster recovery)

**⚠ There is no restore script for the nightly `/data/backups` artifacts.** The
only scripted restore path (`ops/kubera-import.sh`) works from a *migration
bundle* (`ops/kubera-export.sh`'s output), which has a different structure and a
different vault tarball layout. If you have a bundle, use
[§8](#8-migrating-to-a-new-server) instead — it's tested and verified end to end.
The manual procedure below is for the specific case where all you have is a
nightly `db_backup_*.dump` / `vault_backup_*.tar.gz` pair.

```bash
# 0. Stop writers, keep Postgres up.
python3 maintenance.py on
docker compose stop api worker beat
docker compose up -d postgres

# 1. Copy the artifacts out of the backup_data volume onto the host.
docker compose run --rm --no-deps --entrypoint sh api \
  -c 'cat /data/backups/db_backup_<ts>.dump' > ./db_backup_<ts>.dump
docker compose run --rm --no-deps --entrypoint sh api \
  -c 'cat /data/backups/vault_backup_<ts>.tar.gz' > ./vault_backup_<ts>.tar.gz

# 2. Restore the database — custom format needs pg_restore, not psql.
#    --clean --if-exists DROPS existing objects first. Confirm this is the
#    intended target before running it.
cat ./db_backup_<ts>.dump | docker compose exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists --exit-on-error

# 3. Restore the vault. NOTE THE PATH — see the warning below.
cat ./vault_backup_<ts>.tar.gz | docker compose run --rm -T --entrypoint sh api \
  -c 'tar xzf - -C /data'          # -C /data, NOT -C /data/vault

# 4. Fix ownership — containers run as uid 10001, and a manually-populated
#    volume via `docker run --user root` may leave root-owned files.
docker compose run --rm --no-deps --user root \
  --cap-add CHOWN --cap-add DAC_OVERRIDE api \
  chown -R 10001:10001 /data/vault

# 5. Restart and verify.
docker compose up -d
python3 maintenance.py off
```

**⚠ The two vault tarball formats are NOT interchangeable — this is the single
most dangerous mismatch in this whole document:**

| Source | Command | Extract with |
|---|---|---|
| Nightly backup (`app/worker.py`) | `tar -czf <f> -C /data vault` | `-C /data` (contains a `vault/` dir) |
| Migration bundle (`ops/kubera-export.sh`) | `tar czf - -C /data/vault .` | `-C /data/vault` (contents only) |

Extracting a nightly `vault_backup_*.tar.gz` with the bundle-import path's
`-C /data/vault` produces `/data/vault/vault/...` — the application starts
cleanly, every document 404s, and it looks exactly like the vault-volume
migration bug from [§9](#9-one-time-moving-an-old-servers-vault-into-its-volume).
Match the table above to whichever artifact you actually have.

**Practice this before you need it.** An untested backup is a guess — restore
one into a throwaway stack periodically (see [§12](#12-pre-deploy-and-periodic-checklists)).

---

## 8. Migrating to a new server

This is also the tested, scripted disaster-recovery path — prefer it over
[§7](#7-restoring-from-a-backup-disaster-recovery) whenever you have (or can
make) a full export bundle, because it's the one with automated checksum and
row-count verification.

### 8.1 One command, run on the OLD server

```bash
./ops/kubera-migrate.sh ash@NEW-SERVER-IP --domain audit.example-new.com
```

What it does, end to end: exports (maintenance on → freeze writes → dump
Postgres + tar the vault + copy `.env`) → stages a throwaway SSH key on the
target → transfers the bundle and the repo over `rsync --checksum` → runs the
importer on the target, which installs Docker if missing, restores, starts the
stack, and verifies row counts / vault file counts / KEK fingerprint against the
manifest.

**⚠ By default this leaves the OLD server frozen** (api/worker/beat stopped,
maintenance mode on) — correct for an actual cutover (prevents split-brain
writes on two live copies), surprising if you were only testing. Pass
`--keep-live` to keep the source serving throughout.

```bash
./ops/kubera-migrate.sh ash@NEW-SERVER-IP --keep-live --domain audit.example-new.com  # test run, source stays live
```

**Target requirements:** SSH as root or a sudo-capable user; ports 80/443 open
before starting (Let's Encrypt needs them); if the importer adds your user to
the `docker` group mid-run it exits 3 asking you to `newgrp docker` and re-run —
**that re-run is safe**, checksums are re-verified and the restore is idempotent
(`pg_restore --clean --if-exists`).

**⚠ `ops/kubera-import.sh`, which this calls on the target, has three sharp
edges — know them before you run it directly against anything you care about:**
1. It runs `docker stop $(docker ps -q)` — stops **every** running container on
   the target host, not just Kubera's. Fine for a dedicated fresh box, dangerous
   on a shared one.
2. It overwrites the target's `.env` with the bundle's, unconditionally, no
   prompt, no backup of the old one.
3. It deletes the bundle when it finishes (`rm -rf $BUNDLE`) **unless you pass
   `--keep-bundle`**. If this is your only copy, pass `--keep-bundle`.

**After migration:** point DNS at the new server, log in, open a tenant
document — only then retire the old one. Rollback before the DNS flip is
trivial: the old server never stopped serving; `docker compose up -d api worker
beat && python3 maintenance.py off` unfreezes it.

Redis state (sessions, rate-limit counters) is intentionally not migrated —
users just log in again on the new server.

### 8.2 Disaster-recovery snapshot without a target (any time)

```bash
./ops/kubera-export.sh --keep-live       # bundle in ~/kubera-migration-<ts>, source stays live
```

**⚠ Without `--keep-live`, the default, the script freezes the site** (stops
api/worker/beat, enables maintenance) **and leaves it frozen** — it only prints
the unfreeze command, it doesn't run it. If you just wanted a snapshot, always
pass `--keep-live`.

`--no-maintenance` does **not** mean no downtime — it only skips the friendly
maintenance page; `api`/`worker`/`beat` still stop, so users see raw connection
errors instead of a 503.

The bundle (`db.dump`, `vault.tar.gz`, `env`, `manifest.json`, `sha256sums.txt`)
is written with `700`/`600` permissions but is **unencrypted** and contains every
secret in `.env` in cleartext, including `ROOT_MASTER_KEK`. Copy it somewhere
safe and treat it as you would the vault itself.

### 8.3 Restore from a bundle onto any Docker machine

```bash
./ops/kubera-import.sh /path/to/kubera-migration-<ts> --keep-bundle
./ops/kubera-import.sh /path/to/bundle --domain audit.example.com --keep-bundle
```
Verifies checksums **before touching anything**; refuses (`die`, old data
untouched) if they don't match. Compares row counts, vault file counts, and the
KEK fingerprint against the manifest after restoring — if verification fails,
the *target* has already been overwritten (the message "old server untouched"
refers to the export source, not this machine), so only run this against a
target you intend to overwrite.

---

## 9. One-time: moving an old server's vault into its volume

**Only relevant when upgrading a deployment that ran the old bind-mounted
compose file** (i.e., one that predates the hardened `docker-compose.yml`). A
fresh install never needs this — the script detects and no-ops.

**The problem:** an old `.env` may carry a relative `VAULT_STORAGE_PATH=./data/vault`,
which used to resolve against the old `.:/code` bind-mount to a real host
directory. The hardened compose file has no such mount and pins
`VAULT_STORAGE_PATH=/data/vault` inside the `vault_data` named volume. Upgrade
without this step and every document 404s — looks exactly like data loss, isn't.

```bash
ops/kubera-migrate-vault-to-volume.sh              # dry run — counts only, changes nothing
ops/kubera-migrate-vault-to-volume.sh --apply       # never overwrites; host copy untouched
```

Copies with `cp -a -n` (archive mode, never clobber) from a **read-only** mount
of the host directory into the volume, then verifies the post-copy file count is
not less than the source count — if it is, it `die`s without touching the host
copy, "investigate before restarting the stack." Fully idempotent: a second run
copies nothing new and the count check still passes.

**⚠ Requires `--cap-add CHOWN --cap-add DAC_OVERRIDE`** on any manual `--user
root` command that touches these volumes — the containers run with `cap_drop:
ALL`, and `--user root` alone does not undo that:

```bash
docker compose run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE api \
  chown -R 10001:10001 /data/vault /data/backups
docker compose run --rm --no-deps --user root --cap-add CHOWN --cap-add DAC_OVERRIDE beat \
  chown -R 10001:10001 /var/lib/kubera-beat
```
(README's troubleshooting section has an older version of this command without
the `--cap-add` flags — it will fail with "Operation not permitted." Use the
form above.)

**After a successful migration:**
```bash
docker compose up -d --build
# download a document through the UI to confirm decryption still works
tar czf ~/kubera-vault-preupgrade.tar.gz -C "$(dirname "$SRC")" "$(basename "$SRC")"
# keep this archive — don't delete the host copy the same day you migrate
```

---

## 10. Maintenance mode reference

`python3 maintenance.py on|off|status` — no other subcommands, no flags beyond
that. Run from the repo directory; it drives the `gateway` and `caddy` containers
via `docker compose exec`, never restarts them. An exclusive file lock
(`.maintenance.lock`, gitignored) prevents two operators from toggling
concurrently — a second concurrent invocation fails immediately rather than racing.

**Mechanism:** the mode switch is an atomic symlink rename inside the `gateway`
container (`active.conf` → either `app.conf` or `maintenance.conf`), followed by
`nginx -s reload`. Not a container restart, not a file copy.

**`on`:** reconciles Caddy's live config to point at `gateway:80` (refuses if the
mounted `Caddyfile` would bypass the gateway — fix the deployment checkout first),
then flips the symlink. No readiness checks on `frontend`/`api` — maintenance
doesn't need them healthy.

**`off`:** reconciles Caddy the same way, then — **the gate** — runs, from
*inside* the gateway container, `wget` against `http://frontend/index.html` and
`http://api:8000/readyz`. **Any failure refuses to start the countdown; nothing
changes; maintenance stays on.** There is no `--force`. Only after both pass:
a 10-second countdown (hardcoded, not configurable), then the symlink flips back,
verified again.

**`status`** is read-only — never writes state, never reloads anything.
```
Gateway:     valid | INVALID          # does the nginx config in the container parse
Edge route:  gateway:80 | MISMATCH    # is Caddy's LIVE config actually pointing here
Caddy:       valid | INVALID
Frontend:    ready | NOT READY
Api:         ready | NOT READY
```
`Edge route: MISMATCH` is the state to watch for — it means a long-running Caddy
process is serving a stale Caddyfile and **public traffic is bypassing
maintenance mode entirely**. `status` prints the fix (`maintenance.py on`, which
reconciles Caddy as a side effect).

**Failure modes:**
- Running `on` twice, or `off` when already off, is safe and idempotent.
- Ctrl+C **during the countdown** is explicitly handled: maintenance stays on,
  clean exit. Ctrl+C **outside the countdown** (mid-`switch()`) is not handled —
  worst case the symlink points at the new mode before nginx has reloaded it.
  Recovery: re-run `maintenance.py status`, then `on` (or `off`) — `switch()`
  always re-points, reloads, and verifies from scratch, so re-running resolves it.
- **Never `docker compose down` during a maintenance window** — that removes
  Caddy and the gateway, the entire public edge, maintenance page included.

---

## 11. Firewall and exposure verification

```bash
# Dry run first — read the plan, confirm the SSH port is right, THEN apply.
# Do this inside tmux/screen; keep your current SSH session open until a
# second session confirms access still works.
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --apply
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --status

# Emergency undo — leaves the host with NO inbound filtering. Only to recover
# access, e.g. via a serial/rescue console after a lockout:
sudo ./ops/kubera-harden-firewall.sh --ssh-port 22 --revert --apply

# Verify — run both:
./ops/kubera-verify-exposure.sh --local              # on the server: config-level
./ops/kubera-verify-exposure.sh --remote <server-ip>  # from your laptop: ground truth
```

**Why both layers matter:** Docker's published-port DNAT lands in
`nat/PREROUTING`, which is traversed *before* the `filter/INPUT` chain `ufw`/
`firewalld` write to — `ufw deny 5433` reports success and the port stays open.
`DOCKER-USER` is the only hook in front of container ports; the script writes to
both it and `INPUT`.

**Known limits, not covered by this script:** IPv4 only (no `ip6tables` rules —
currently benign since only Caddy publishes a port, but any future `ports:`
entry needs IPv6 rules added manually); the RFC1918-source allowlist in
`DOCKER-USER` could in principle be bypassed by a spoofed private source address
from the internet (BCP38 normally prevents this, but the script can't guarantee
it) — configure your **provider's** network firewall (AWS security group,
DigitalOcean/Hetzner cloud firewall) to allow only 22/80/443 as well; it filters
before traffic reaches the host and sidesteps this class of problem entirely.

`--status` requires nothing (no `--ssh-port`). Apply/revert/plan all require an
explicit `--ssh-port` — the script refuses to run without one, specifically so
it can't lock you out by guessing wrong.

Also run the static checks, cheap and worth having in any pre-deploy gate:
```bash
uv run pytest unit_tests/test_compose_exposure.py unit_tests/test_config_secrets.py \
  unit_tests/test_deployment_hardening.py -q
```

---

## 12. Pre-deploy and periodic checklists

**Before every deploy:**
- [ ] `uv run pytest unit_tests -q` (fast; the full backend suite is not required
      for a routine deploy — run the modules touched by the change)
- [ ] No `docker-compose.override.yml` on the server
- [ ] `KUBERA_ALLOW_INSECURE_DEFAULTS` is not set anywhere in the server's environment
- [ ] If the change touches `gateway/`, the build command includes `gateway`
      ([§3.2](#32-routine-update-deploy-zero-downtime-existing-server))
- [ ] If the change adds a migration, take a backup first
      (`./ops/kubera-export.sh --keep-live`)

**After every deploy:**
- [ ] `docker compose ps` — every service healthy
- [ ] `docker compose exec api id` — `uid=10001(kubera)`, confirms the image
      didn't regress to running as root
- [ ] Log in and open a tenant document — the one check that exercises the
      whole KEK chain
- [ ] `python3 maintenance.py status` — `Edge route: gateway:80`, not a mismatch

**Periodically (monthly is reasonable):**
- [ ] `./ops/kubera-verify-exposure.sh --remote <server-ip>` from off-box
- [ ] `sudo ./ops/kubera-harden-firewall.sh --ssh-port <port> --status` — confirm
      the rules survived any reboots since the last check
- [ ] `docker compose exec api sh -c 'ls -la /data/backups | tail'` — confirm
      recent backups exist **and check the byte counts**, not just presence
- [ ] Restore a backup into a throwaway stack. An untested backup is a guess.
- [ ] Confirm `ROOT_MASTER_KEK` is backed up somewhere that is neither this
      server nor this server's database backup
- [ ] Consider rotating `JWT_SECRET_KEY` / `INTERNAL_API_KEY` on whatever
      cadence your threat model calls for — both are cheap, hard cutovers with
      no data at risk ([§5.2](#52-jwt_secret_key), [§5.3](#53-internal_api_key))

---

## 13. Known gaps — do not assume these are covered

Documenting these honestly is safer than a runbook that implies more automation
exists than actually does:

- **No production `alembic downgrade` path.** See [§4.3](#43-if-a-migration-goes-wrong).
  Restoring a pre-migration backup is the real rollback.
- **No restore script for the nightly `/data/backups` artifacts** — only for
  migration bundles. [§7](#7-restoring-from-a-backup-disaster-recovery) is a
  manual procedure, not a tested script.
- **`maintenance.py` has no `--force`.** If `off` refuses because `frontend` or
  `api` genuinely can't come up, there is no supported way to force the public
  route back without first making them healthy (or manually manipulating the
  symlink inside the gateway container, which is outside any tested path).
- **Firewall and KEK-rotation scripts have limited field verification** — the
  firewall script has not been exercised against every possible distro's
  persistence mechanism; the KEK rotation script has been verified against a
  real multi-company production database exactly once (2026-09-01, see
  `SECURITY_HARDENING.md` §"Verification provenance").
- **Uploads have no size limit** (`client_max_body_size 0`), and `docvault.py`
  reads an upload fully into memory before encrypting — an authenticated user
  can push the `api` container toward its 1 GB memory limit. The limit contains
  the damage to one container; a real cap and streaming encryption are outstanding.
- **No Content-Security-Policy** — `X-Frame-Options: DENY` is used instead,
  deliberately, because a `srcdoc` iframe (`AssetReportsPage.tsx`'s report
  preview) inherits its parent's CSP and a `frame-ancestors` directive would
  blank the preview.
- **Base images float** (`postgres:16-alpine`, `caddy:2-alpine`, …) — two builds
  of the same commit are not guaranteed byte-identical.

If you close one of these gaps, update this section rather than deleting it
silently — the next operator needs to know the ground shifted.
