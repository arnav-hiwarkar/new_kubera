# Server Migration & DR Tooling — Design

Date: 2026-08-26
Status: Approved (pending implementation plan)

## Context

Kubera runs on a single server as a Docker Compose stack. All state lives on that machine:

| State | Where | Notes |
|---|---|---|
| Relational data | `pgdata` volume (Postgres 16) | Users, companies, engagements, metadata |
| Encrypted tenant files | `vault_data` volume → `/data/vault` | ~1200+ per-tenant dirs; encrypted with `ROOT_MASTER_KEK` |
| Nightly backups | `backup_data` volume → `/data/backups` | Celery beat: plain SQL dump + vault tarball |
| Secrets | `.env` | `ROOT_MASTER_KEK`, `JWT_SECRET_KEY`, DB creds, `INTERNAL_API_KEY`, `DOMAIN` |
| TLS certs | `caddy_data` / `caddy_config` volumes | Re-issuable, not worth transferring |
| Gateway mode | `maintenance_runtime` volume | Trivial; not transferred |

Cloning the repo on a new server gives code but no data — and without copying `.env`
(specifically `ROOT_MASTER_KEK`), every vault file on the new server would be undecryptable.
There is no end-to-end, verified procedure for moving a live deployment to a new server.

## Goals

- One command migrates a running Kubera instance to a bare Ubuntu server: data, secrets,
  code, and stack startup included.
- Maintenance window acceptable (gateway maintenance mode during export); no near-zero-downtime
  requirement.
- Data travels directly server-to-server over SSH (never through a third machine).
- The new server needs zero manual preparation — Docker install, repo placement, restore,
  and startup are automated.
- The same tooling doubles as ongoing disaster-recovery backup/restore.
- Domain-flexible: deploy under a different domain today, redeploy under the original
  domain on future servers.

## Non-goals

- Near-zero-downtime migration via Postgres streaming replication / continuous vault sync
  (future work; noted in "Future").
- Migrating Redis state (ephemeral cache/broker), Caddy TLS state (re-issued automatically),
  or historical nightly backups (optional flag only).
- Scheduled/offsite snapshot rotation (existing Celery nightly backups remain unchanged).

## Approach

Three shell scripts in a new `ops/` directory:

1. **`ops/kubera-export.sh`** *(source server)* — produces a self-contained, checksummed bundle:
   Postgres dump + vault tarball + `.env` + manifest.
2. **`ops/kubera-import.sh`** *(target server)* — sets up a fresh box from a bundle: installs
   Docker if missing, places the repo, restores DB and vault, starts and verifies the stack.
3. **`ops/kubera-migrate.sh`** *(source server)* — orchestrator: runs export locally, transfers
   bundle + repo tree over SSH, triggers import remotely, reports verification results.

Raw-volume replication (rsyncing Docker's internal volume dirs) was rejected: it couples to
Docker storage internals, requires identical Postgres versions, offers no integrity checking,
and cannot serve disaster recovery. Live replication was deferred as out of scope given an
accepted maintenance window.

## Bundle layout

```
kubera-migration-<YYYYMMDD-HHMMSS>/
├── db.dump              # pg_dump -Fc (custom format, compressed)
├── vault.tar.gz         # tar.gz of the entire vault_data volume content
├── env                  # copy of source .env (secrets incl. ROOT_MASTER_KEK)
├── manifest.json        # git SHA, table row counts, vault file count, KEK fingerprint
└── sha256sums.txt       # SHA256 of every artifact above
```

Bundles are created with `700` dir / `600` file permissions (they contain secrets and all
tenant data). Default location: `~/kubera-migration-<ts>/`.

## Flow

### Export (`kubera-export.sh`, run on source)

1. Toggle gateway **maintenance mode ON** (reuses existing `maintenance.py` mechanism) unless
   `--no-maintenance`.
2. Stop `api`, `worker`, `beat` containers (Postgres stays up for the dump; stopping app
   services freezes writes so DB and vault are mutually consistent).
3. Dump Postgres with `pg_dump -Fc`; tar the vault volume into `vault.tar.gz`; copy `.env`.
4. Write `manifest.json`: source commit SHA, row counts of key tables, vault file/dir count,
   SHA256 fingerprint of `ROOT_MASTER_KEK`, timestamps.
5. Write `sha256sums.txt` over all artifacts.
6. Unless `--keep-live`: leave old stack stopped (cutover imminent). With `--keep-live`,
   restart app containers and toggle maintenance OFF after export completes.

### Transfer (`kubera-migrate.sh`, run on source)

1. Generate a throwaway SSH keypair on the source server; append the public key to the target's
   `authorized_keys` via the operator-provided SSH login (`user@target`). Key is removed again
   at the end (success or failure).
2. `rsync --partial --checksum` the bundle and the repo working tree (excluding `.venv`,
   `node_modules`, `.git`, caches) directly to the target. Re-running resumes interrupted
   transfers rather than restarting them.
3. Trigger import remotely over SSH and stream its output back.

The repo tree is rsync'd rather than cloned on the target so the new server runs the *exact*
same version as the source (including uncommitted fixes), with no Git credentials required there.

### Import (`kubera-import.sh <bundle-dir> [--domain DOMAIN]`, run on target)

Preconditions checked first — any failure aborts with a clear error before anything is modified:

- Bundle checksums match `sha256sums.txt`; `.env` present with non-empty `ROOT_MASTER_KEK`;
  Ubuntu with apt available.

Then, in order:

1. Install **Docker Engine + Compose v2 plugin + git** via apt if missing.
2. Place the rsync'd repo tree at `~/kubera` (configurable).
3. Install bundle `env` as `.env`; rewrite `DOMAIN=` when `--domain` is given.
4. Create named Docker volumes; start only Postgres; create the database; restore with
   `pg_restore --no-owner`; then untar vault content into the `vault_data` volume.
5. `docker compose up -d` (full stack); wait for container healthchecks.
6. Verify against `manifest.json`: `/readyz` responds through the gateway; key-table row counts
   match; vault file count matches; KEK fingerprint matches.
7. Print a verification report (counts compared side-by-side).
8. Delete the bundle from the target unless `--keep-bundle` (it duplicates live data and holds
   secrets).

## Domain & TLS

Caddy provisions and renews Let's Encrypt certificates automatically. Requirements are only:
correct `DOMAIN=` in `.env` (set by `--domain`), DNS A record pointing at the new server, and
ports 80/443 open. No manual cert steps.

Rules:

- Different domain now: pass `--domain new.example.com` to migrate/import.
- Original domain later (this or future servers): set `DOMAIN`, point DNS at that server, done.
- Never let two servers serve the same domain simultaneously (split-brain); avoid rapid
  domain flipping (Let's Encrypt rate limits).

## Failure handling & rollback

- Every stage is re-runnable; nothing destructive happens until verification passes.
- Import verifies checksums *before* restoring; aborts cleanly on mismatch or missing secrets.
- Source stack is never modified destructively: it restarts intact at any point with
  `docker compose up -d` + maintenance off.
- Rollback is DNS: until the A record moves, the old server keeps serving and there is nothing
  to undo. After cutover, roll forward on the new server instead.
- Throwaway SSH key is removed on both success and failure paths.

## Disaster-recovery reuse

The identical bundle doubles as an on-demand full-system snapshot:

- `ops/kubera-export.sh` alone = "make a full verified backup." It follows the same
  write-freeze procedure as migration (maintenance mode + stop app services) so DB and vault
  are mutually consistent; schedule snapshots in low-traffic windows.
- `--no-maintenance` skips the user-facing maintenance page while still stopping app services
  (brief API unavailability, no countdown page).
- `ops/kubera-import.sh <bundle-dir>` on any machine (including the same one after corruption)
  = "restore." Restore is location-independent; no separate DR tooling exists.
- Existing nightly Celery backups remain unchanged.

## Security notes

- Bundles contain all tenant data plus every secret. Created `700`/`600`; transferred only over
  SSH; deleted from the target after successful verification.
- No credentials are shared between old and new servers beyond the temporary SSH key, which is
  scoped to the operator account and removed afterwards.
- Nothing transits the operator's laptop or any third-party medium.

## CLI sketch

```bash
# Full migration (run on OLD server, repo root):
./ops/kubera-migrate.sh ash@203.0.113.10 --domain audit.example-new.com

# Options (all scripts): --dry-run prints actions without executing mutating steps;
# --keep-live keeps old stack serving after export; --skip-setup assumes Docker+git exist;
# --keep-bundle retains the bundle on the target; --dest PATH overrides ~/kubera.

# DR snapshot (run on any server):
./ops/kubera-export.sh

# Restore from a bundle (run on target machine, any location):
./ops/kubera-import.sh ./kubera-migration-20260826-153000
```

## Testing

1. **Roundtrip rehearsal (local)**: export from the current dev stack; import into scratch
   directories/volumes; verify `/readyz`, log in, open a tenant document — proves the dump/
   restore path including KEK correctness.
2. **Dry-run mode**: exercised for each script.
3. **Bare-box rehearsal**: full `migrate.sh` onto the real target Ubuntu box using a throwaway
   domain before production cutover.

## Future

- Approach C: near-zero-downtime migrations via Postgres streaming replication plus continuous
  vault sync, with a brief pause-and-cutover step replacing the maintenance window.
