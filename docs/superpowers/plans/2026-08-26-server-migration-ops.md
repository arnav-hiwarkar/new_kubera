# Server Migration & DR Ops Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-command, checksum-verified migration of a running Kubera server to a bare Ubuntu server (data + secrets + code + stack startup), reusable as disaster-recovery backup/restore.

**Architecture:** Three bash scripts in `ops/` sharing `ops/lib.sh`.
- `kubera-export.sh` freezes writes and produces a bundle (`pg_dump -Fc`, vault tarball, `.env`, manifest, SHA256 sums) with zero container-state fragility.
- `kubera-migrate.sh` transfers bundle + repo tree server-to-server over SSH with a throwaway key, then remotely invokes `kubera-import.sh`.
- `kubera-import.sh` sets up Docker on the target, restores database and vault files, rewrites domain if requested, starts all services, and verifies against the manifest.
Spec: `docs/superpowers/specs/2026-08-26-server-migration-design.md`.

**Tech Stack:** Bash (Ubuntu 20.04–24.04 hosts / macOS), Docker Compose v2, rsync, SSH, Python 3 (present on hosts; used for JSON manifest read/write), pytest + subprocess for script tests.

## Global Constraints

- All ops scripts are `#!/usr/bin/env bash` with `set -euo pipefail`, run on the Docker **host** from the repository root.
- Secrets discipline: never print `.env` values. Only ever print `kek_fingerprint` (first 16 hex chars of SHA256 of `ROOT_MASTER_KEK`).
- Source data immutability: old server data is strictly read-only and never deleted or mutated.
- Bundle layout is fixed: `db.dump`, `vault.tar.gz`, `env`, `manifest.json`, `sha256sums.txt` inside `kubera-migration-<YYYYMMDD-HHMMSS>/`.
- Every mutating action goes through `dr_run` so `--dry-run` prints `DRYRUN:` + the command instead of executing it.
- Tests run with `.venv/bin/pytest tests/test_ops_*.py -v`.

---

### Task 1: Harden Export Script `ops/kubera-export.sh`

**Files:**
- Modify: `ops/kubera-export.sh`
- Test: `tests/test_ops_export.py`

**Objectives:**
- Eliminate reliance on pre-existing `API_CID` or `docker compose ps -q api`.
- Use `docker compose run --rm --no-deps -T --entrypoint sh api` for archiving `/data/vault` and counting files.
- Ensure stopped/frozen/fresh stacks can export without errors.
- Ensure dry-run prints clean output and tests pass.

- [ ] **Step 1: Update `ops/kubera-export.sh` to remove `API_CID` and use Compose run**
- [ ] **Step 2: Update `tests/test_ops_export.py` assertions for dry-run output**
- [ ] **Step 3: Run pytest on export tests: `.venv/bin/pytest tests/test_ops_export.py -v`**
- [ ] **Step 4: Commit changes**

---

### Task 2: Verify & Harden Import Script `ops/kubera-import.sh`

**Files:**
- Modify: `ops/kubera-import.sh`
- Test: `tests/test_ops_import.py`

**Objectives:**
- Ensure `restore_vault` extracts into `/data/vault` idempotently.
- Ensure `restore_db` runs `pg_restore` with `--clean --if-exists`.
- Ensure domain rewrite via `apply_domain` cleanly updates `.env`.
- Ensure healthcheck polling and manifest verification run smoothly.

- [ ] **Step 1: Verify `ops/kubera-import.sh` implementation**
- [ ] **Step 2: Run pytest on import tests: `.venv/bin/pytest tests/test_ops_import.py -v`**
- [ ] **Step 3: Commit changes if any edits were made**

---

### Task 3: Verify & Harden Migration Orchestrator `ops/kubera-migrate.sh`

**Files:**
- Modify: `ops/kubera-migrate.sh`
- Test: `tests/test_ops_migrate.py`

**Objectives:**
- Verify `--domain <NEW_DOMAIN>` CLI option passing.
- Verify throwaway SSH key generation, deployment, and cleanup trap on exit/failure.
- Verify rsync exclusions (`.venv`, `node_modules`, `.git`, `__pycache__`, `.maintenance.lock`).
- Verify remote import execution and checklist output.

- [ ] **Step 1: Verify `ops/kubera-migrate.sh` implementation**
- [ ] **Step 2: Run pytest on migration tests: `.venv/bin/pytest tests/test_ops_migrate.py -v`**
- [ ] **Step 3: Run full ops test suite: `.venv/bin/pytest tests/test_ops_*.py -v`**
- [ ] **Step 4: Commit changes**

---

### Task 4: Complete Operator Runbook & Execution Instructions

**Files:**
- Modify: `README.md` (if needed)
- Output: Exact operator commands for unfreezing source server, pulling latest changes, and running the single-command migration.

- [ ] **Step 1: Verify all 4 ops scripts have executable permissions (`chmod +x ops/*.sh`)**
- [ ] **Step 2: Commit any final updates**
- [ ] **Step 3: Provide clear, end-to-end operator instructions for migration cutover**
