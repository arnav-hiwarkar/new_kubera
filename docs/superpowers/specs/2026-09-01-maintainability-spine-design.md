# Maintainability — the enforcement spine

Sub-project 1 of 4. Establishes the tooling, CI pipeline and invariant registry
that the remaining three sub-projects plug into.

**Decisions taken during brainstorming** (these constrain everything below):

| Decision | Choice |
|---|---|
| Primary documentation audience | AI agents first, maintainer second |
| Enforcement model | Tiered — fast local, blocking on PR, advisory nightly |
| "Anti-tests" means | Negative tests + abuse-case tests. Not mutation testing, not fuzzing. |
| E2E security target | Two tiers — in-process on PR, live stack nightly |
| Sequencing | Spine → security assurance → navigability → devsecops |
| CI host | GitHub Actions |
| Branch flow | PR required to `main`, CI must pass |

---

## 0. Context

`docs/SECURITY_AUDIT_2026-09-01.md` recorded 40 findings. Roughly 40 changes to
security-critical code are about to be made by a single developer with **no CI,
no linter, and no second reviewer** (249 of 252 commits are one author).

Two facts shape this design:

1. **There is no second pair of eyes.** Every checklist that depends on "someone
   reviews this" will not hold. Enforcement has to be executable.
2. **The codebase already demonstrates the right instinct.**
   `unit_tests/test_compose_exposure.py` turns "only Caddy may publish a port"
   into a test that fails when the rule is broken.
   `unit_tests/test_dockerignore_covers_secrets.py` does the same for image
   contents. This spec generalises that pattern rather than inventing one.

**The governing principle: an invariant is either executable or it rots.**

---

## 1. The umbrella (context only — not built here)

```
                    ┌─────────────────────────────┐
                    │   INVARIANT REGISTRY         │
                    │   INV-xxx ⇄ exactly one test │
                    └──────────────┬──────────────┘
   ┌───────────────┬───────────────┼────────────────┬───────────────┐
   │  1. SPINE     │  2. SECURITY  │ 3. NAVIGABILITY│ 4. DEVSECOPS  │
   │  (this spec)  │   ASSURANCE   │                │               │
   ├───────────────┼───────────────┼────────────────┼───────────────┤
   │ ruff, mypy    │ authz matrix  │ AGENTS.md tree │ live-stack E2E│
   │ pre-commit    │ negative tests│ docstring conv.│ trivy, gitleaks│
   │ GH Actions    │ abuse cases   │ docs restructure│ pip-audit    │
   │ test taxonomy │ 30 audit tests│ generated maps │ checklist skills│
   │ migration CI  │ OWASP coverage│ ADRs           │ nightly gates │
   └───────────────┴───────────────┴────────────────┴───────────────┘
```

Each sub-project gets its own spec and plan. This one builds only the spine.

---

## 2. One command, three tiers

### Problem

There is no canonical way to run checks. An agent or a returning maintainer has
to infer commands from `pyproject.toml` and `package.json`, and any command they
invent will differ from what CI runs — so "passes locally" means nothing.

### Design

A `justfile` at the repository root is the single entry point. **CI invokes the
same recipes**, so local and CI behaviour cannot diverge.

| Recipe | Trigger | Budget | Contents |
|---|---|---|---|
| `just fast` | pre-commit hook | < 5 s | ruff format + lint on staged files, gitleaks on staged diff |
| `just check` | PR — **blocks merge** | < 5 min | ruff, `unit_tests/`, `tests/` (Postgres + Redis), frontend lint + `tsc -b` + vitest, migration checks, invariant-registry check |
| `just deep` | nightly — advisory | minutes | placeholder; populated by sub-projects 2 and 4 |

`just` is chosen over `make` because recipes are plain shell with no tab/phony
semantics, which matters when an agent edits the file.

Every recipe is also runnable in isolation (`just lint`, `just test-unit`,
`just test-integration`, `just frontend`, `just migrations`) so a failing tier
can be re-run narrowly.

### Acceptance

- `just check` passes on a clean checkout of `main`.
- `.github/workflows/ci.yml` contains no test commands of its own — it calls
  `just` recipes only.
- Running `just` with no arguments lists available recipes.

---

## 3. Python tooling baseline

### Problem

No linter, no formatter, no type checking. Style is inconsistent across 25,753
lines, and defects that a linter catches for free (unused imports, shadowed
names, bare `except`) currently reach `main`.

### Design

**Ruff** for both lint and format — one tool replacing black, flake8 and isort.
Configured in `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "S", "ASYNC", "C4", "SIM"]
ignore = [
    "E501",   # line length is handled by the formatter
    "S101",   # assert is correct in tests
    "B008",   # FastAPI Depends() in defaults is the framework idiom
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S", "B"]
"unit_tests/*" = ["S", "B"]
"alembic/versions/*" = ["E", "F", "I"]   # generated; churn is not worth it
```

`S` (flake8-bandit) is included deliberately: it catches hardcoded secrets, weak
hashes and `shell=True` — the classes of defect this project cares most about.

**Adoption is a single formatting commit**, made separately from any behavioural
change so the diff stays reviewable.

**Mypy** is included but **advisory only and scoped to `app/services/`**. Pointing
a type checker at 25 k lines produces hundreds of errors and gets switched off
within a week. `app/services/` is pure logic, already well annotated, and is the
highest-value place to start. Scope expands by deliberate decision, one package
at a time, never by turning on a flag.

**Coverage** is measured with `pytest-cov` and reported in the PR summary, but is
**not** a hard gate. A coverage percentage rewards testing trivial getters; the
invariant registry (§5) is the real correctness signal. The one exception, added
in sub-project 2: coverage must not *decrease* on files under `app/auth.py`,
`app/routers/auth.py` and `app/services/`.

### Acceptance

- `ruff check .` and `ruff format --check .` both pass.
- `mypy app/services/` runs in CI and reports without failing the build.
- A PR that adds an unused import fails `just check`.

---

## 4. Test taxonomy

### Problem

Tests split across `tests/` (needs a database) and `unit_tests/` (pure) with no
declared meaning, no way to select a category, and no marker vocabulary for the
negative and abuse-case tests that sub-project 2 will add.

### Design

**Keep both directories.** The split is real and useful — pure vs.
database-backed. Renaming 73 files buys nothing and destroys `git blame`.
Document the meaning instead:

- `unit_tests/` — no database, no network, no filesystem beyond `tmp_path`.
  Budget: **under 5 seconds total**. Measured baseline is 0.9 s for the existing
  354 tests plus ~1.4 s for the invariant-registry check, which collects the full
  suite. Collection does not execute fixtures, so it needs no database.
- `tests/` — integration; real Postgres and Redis, exercised through the ASGI app.

Layer categories on with **pytest markers**, registered in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "invariant(id): enforces a registered invariant from docs/INVARIANTS.md",
    "negative: asserts a forbidden operation is refused",
    "abuse: attacker-goal scenario derived from a security finding",
    "edge: boundary, degenerate or malformed input",
    "slow: excluded from `just check`; runs in `just deep`",
]
```

This makes `pytest -m abuse` and `pytest -m "negative or abuse"` work, and gives
the registry check (§5) something to bind to. A `--strict-markers` setting means
a typo in a marker name fails rather than silently selecting nothing.

### Acceptance

- `pytest -m negative` and `pytest -m abuse` run without error (empty is fine
  until sub-project 2 populates them).
- An unregistered marker fails collection.
- `unit_tests/` completes in under 5 seconds.

---

## 5. The invariant registry

### Problem

Rules live in three incompatible places: prose that goes stale
(`SECURITY_HARDENING.md`), comments that get deleted with the code they describe,
and tests that enforce a rule without saying which rule. Nothing connects them,
so `docs/TECHNICAL_REFERENCE.md` grew to 94 KB and cannot be trusted.

### Design

Every security or architectural rule gets an ID, one sentence, and **exactly one
test**. `docs/INVARIANTS.md` holds the table:

```markdown
| ID | Invariant | Enforced by | Origin |
|---|---|---|---|
| INV-001 | Only the `caddy` service may publish a port to a wildcard address. | `unit_tests/test_compose_exposure.py::test_no_wildcard_ports` | SECURITY_HARDENING §4.1 |
| INV-002 | Nothing `.gitignore` treats as secret may enter the Docker build context. | `unit_tests/test_dockerignore_covers_secrets.py::test_secrets_excluded` | Incident: shipped credentials + 3013 vault files |
| INV-003 | Every module in `MODULE_DEFINITIONS` is enforced server-side, not only by `ModuleGuard.tsx`. | `tests/test_module_enforcement.py::test_every_module_router_has_a_server_side_gate` | KUB-001 |
```

Tests declare their ID:

```python
@pytest.mark.invariant("INV-003")
def test_every_module_router_has_a_server_side_gate(): ...
```

`unit_tests/test_invariant_registry.py` enforces the binding **bidirectionally**:

1. Every row in `INVARIANTS.md` names a test node that **exists and is collectable**.
2. Every `@pytest.mark.invariant("INV-x")` in the suite has a matching row.
3. IDs are unique, sequential and never reused.
4. Every invariant has a non-empty Origin.

Verification uses pytest's collection API (`--collect-only -q`) rather than
grepping for function names, so a renamed or deleted test is caught rather than
silently passing.

**Why this is the load-bearing piece.** Documentation cites `INV-003` instead of
restating the rule. Deleting the test fails CI. Deleting the registry row fails
CI. Renaming the test fails CI. Prose cannot drift from behaviour, because prose
no longer contains the behaviour — only a pointer to it.

**Seeding.** Three invariants at build time: the two that already exist as tests
(INV-001, INV-002) plus one new one proving the mechanism works end to end.
Sub-project 2 converts the audit's 40 findings into the rest.

### Acceptance

- Deleting a row from `INVARIANTS.md` while its test remains → `just check` fails.
- Renaming a registered test without updating the registry → `just check` fails.
- Adding `@pytest.mark.invariant("INV-999")` with no registry row → `just check` fails.
- A duplicate ID → `just check` fails.

---

## 6. Migration safety in CI

### Problem

`docker-compose.yml` runs `alembic upgrade head` inside the API's start command
under `restart: unless-stopped` (audit KUB-017). Two migrations break out of
their transaction and are not idempotent, so a partial failure becomes a crash
loop. Model/database drift already exists and went unnoticed (KUB-018: the
PostgreSQL `user_role` enum has a value the Python enum cannot load).

Nothing currently catches any of this before deploy.

### Design

Three checks, split by whether they need a database — a file in `unit_tests/`
cannot require one (§4):

- `unit_tests/test_migration_safety.py` — check 1 only (pure; reads the script
  directory from disk).
- `tests/test_migration_safety.py` — checks 2 and 3 (need Postgres).

1. **Single head.** `ScriptDirectory.get_heads()` returns exactly one revision.
   Catches a branched history at the moment it is created rather than at deploy.
2. **No model/database drift.** `alembic.autogenerate.compare_metadata` against a
   freshly migrated scratch database returns empty. Catches a model change
   without a migration, and a migration that does not match the model — which is
   exactly the KUB-018 class of defect.
3. **Round trip.** `upgrade head` → `downgrade base` → `upgrade head` against a
   scratch database succeeds. Proves the rollback path that the audit noted has
   never been exercised.

Checks 2 and 3 run in the integration job against the CI Postgres service, using
a **scratch database** created and dropped per run — never the shared test
database, so a failed downgrade cannot poison other tests.

These are registered as invariants (INV-004…006) so they inherit the registry's
protection against silent deletion.

### Acceptance

- Adding a column to a model without a migration → `just check` fails.
- Creating a second head → `just check` fails.
- A migration whose `downgrade()` is broken → `just check` fails.

---

## 7. GitHub Actions pipeline

### Problem

No CI exists. Correctness depends entirely on the author remembering to run
things.

### Design

`.github/workflows/ci.yml`, triggered on `pull_request` and `push` to `main`.
Four parallel jobs so a lint failure surfaces in seconds rather than after the
integration suite:

| Job | Needs services | Runs | Approx |
|---|---|---|---|
| `lint` | — | `just lint` (ruff check + format check), `mypy` advisory | ~20 s |
| `unit` | — | `just test-unit` (`unit_tests/`, includes registry + compose + dockerignore checks) | ~30 s |
| `integration` | Postgres 16, Redis 7 | `alembic upgrade head`, `just test-integration`, `just migrations` | 2–4 min |
| `frontend` | — | `npm ci`, eslint, `tsc -b`, vitest | ~1 min |

Service containers are pinned to the same major versions as `docker-compose.yml`
(`postgres:16-alpine`, `redis:7-alpine`) so CI tests what production runs.

`KUBERA_ALLOW_INSECURE_DEFAULTS=1` is set for CI only — this is the documented
escape hatch in `app/config.py`, and `conftest.py` already sets it.

**Secret scanning** (`gitleaks`) runs in the `lint` job with full history fetch
on pushes to `main`. Given this repository previously shipped live credentials
inside an image, this is a hard gate, not advisory.

`.github/workflows/nightly.yml` is created as a **stub** on a cron schedule that
invokes `just deep` (currently a no-op). Sub-projects 2 and 4 fill it in. It is
created now so the schedule and permissions are proven before there is anything
depending on them.

**Branch protection** on `main`: require a PR, require all four jobs green,
require the branch to be up to date. Configured through the GitHub UI or
`gh api`; the required settings are recorded in `AGENTS.md` so the configuration
is reproducible rather than tribal knowledge.

### Acceptance

- A PR with a lint error is blocked, and the failure is visible in under a minute.
- A PR that breaks an integration test cannot be merged.
- A PR that commits a `.env` file is blocked by gitleaks.
- `main` cannot be pushed to directly.

---

## 8. Pre-commit

### Problem

Without a local hook, the first feedback on a formatting or secret error is a CI
failure minutes later — which trains people to skip CI, not to fix the error.

### Design

`.pre-commit-config.yaml` with a deliberately **short** hook list. The budget is
5 seconds; anything slower gets bypassed with `--no-verify` and then the hook
protects nothing.

- `ruff` (fix) and `ruff-format` on staged Python
- `gitleaks protect --staged` — the secret gate, mirroring CI
- `check-added-large-files` (2 MB) — the repository already carries a 336 KB PDF
  and a 104 KB generated HTML; this stops the next one
- `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`

**Explicitly not in pre-commit:** any test run, mypy, or the frontend build.
Those belong in `just check`.

Installation is a documented one-liner in `AGENTS.md`; it is not enforced,
because CI is the real gate and a hook that cannot be bypassed is a hook that
gets uninstalled.

### Acceptance

- `pre-commit run --all-files` passes on a clean checkout.
- Staging a file containing a credential is blocked locally.
- The hook completes in under 5 seconds on a typical commit.

---

## 9. Root `AGENTS.md`

### Problem

There is no entry point. An agent starting work must infer the commands, the test
layout, the conventions and the hazards from source. That inference is
re-performed every session and is sometimes wrong.

### Design

A **short** root `AGENTS.md` — under 150 lines. It is not documentation of the
system; that is sub-project 3. It answers only what an agent needs in the first
30 seconds:

1. What this project is, in two sentences.
2. How to run the three tiers.
3. The test taxonomy and the marker vocabulary.
4. **The invariant rule**: security-relevant behaviour is changed only by
   changing its invariant and its test.
5. Where things live — a 10-line map of `app/`, `tests/`, `ops/`, `docs/`.
6. Hazards, each one line with a pointer:
   - `ROOT_MASTER_KEK` changes require `ops/kubera-rotate-root-kek.py` first
   - migrations are not auto-applied by CI and two are not idempotent
   - `docker-compose.override.yml` must never exist on a server
   - `.env` and vault directories must never enter the build context

Written as instructions, not prose. Every claim either points at a file or a
command that can be run.

Per-directory `AGENTS.md` files are **out of scope here** — sub-project 3.

### Acceptance

- An agent given only `AGENTS.md` can run all three tiers correctly.
- It is under 150 lines.
- Every command in it executes successfully on a clean checkout.

---

## 10. Files touched

**New:**

```
justfile
.pre-commit-config.yaml
.github/workflows/ci.yml
.github/workflows/nightly.yml
AGENTS.md
docs/INVARIANTS.md
unit_tests/test_invariant_registry.py
unit_tests/test_migration_safety.py     single-head check (pure)
tests/test_migration_safety.py          drift + round-trip checks (needs Postgres)
```

**Modified:**

```
pyproject.toml          ruff, mypy, coverage, pytest markers, dev deps
pytest.ini              deleted; `[tool.pytest.ini_options]` in pyproject.toml
                        already carries identical `asyncio_mode` and `pythonpath`
                        values, and pytest.ini currently shadows it
unit_tests/test_compose_exposure.py           + @pytest.mark.invariant("INV-001")
unit_tests/test_dockerignore_covers_secrets.py + @pytest.mark.invariant("INV-002")
README.md               point at AGENTS.md for development workflow
```

**Separate mechanical commit:** `ruff format` across the tree. Kept apart from
every behavioural change so both diffs stay reviewable.

---

## 11. Out of scope

Deliberately excluded, with the sub-project that owns each:

| Excluded | Owner |
|---|---|
| Writing the authz matrix, negative tests, abuse cases, the ~30 audit regression tests | Sub-project 2 |
| OWASP coverage mapping, endpoint conformance testing | Sub-project 2 |
| Per-directory `AGENTS.md`, docstring conventions, restructuring the 94 KB reference, ADRs | Sub-project 3 |
| Live-stack E2E, trivy, pip-audit, checklist skills in `.claude/skills/` | Sub-project 4 |
| Fixing any of the 40 audit findings | Separate work, enabled by this |
| Mutation testing, property/fuzz testing | Rejected during brainstorming |
| Coverage percentage *thresholds* (e.g. "must be ≥80%") | Rejected — rewards testing trivia. Distinct from the non-decrease ratchet on security-critical files, which sub-project 2 adds. |
| Renaming `tests/` and `unit_tests/` | Rejected — churn without benefit |

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| The formatting commit collides with in-flight branches | Land it immediately after merging or closing open work; it is mechanical and `git checkout --theirs` resolves conflicts cheaply |
| Integration job is flaky, training the author to ignore red CI | Pin service container versions; no `sleep`-based waits — use health checks; a flaky test is quarantined with `@pytest.mark.slow` and fixed, never re-run until green |
| `just` is an extra dependency to install | Single static binary, available via brew/cargo/apt; `AGENTS.md` documents install. Fallback: recipes are plain shell and can be copied |
| Branch protection is self-imposed and gets disabled under pressure | Accepted. The PR diff is the value even when self-merging; §7 keeps the gate honest but the author can always override in a genuine emergency |
| `S` (bandit) rules produce noise on existing code | Triage once during adoption; genuine findings get fixed, false positives get a `noqa` with a reason comment, not a blanket ignore |
