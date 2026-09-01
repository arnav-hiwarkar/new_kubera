# Maintainability roadmap — ideas parking lot

**Status: NOT STARTED. Do the security fixes from `docs/SECURITY_AUDIT_2026-09-01.md`
first.** This file exists so nothing from the 2026-09-01 brainstorming session is
lost before this work is picked back up. It is notes and options, not a committed
plan — sub-project 1 is the only one with a real spec
(`docs/superpowers/specs/2026-09-01-maintainability-spine-design.md`), and even
that has not been built yet.

When you're ready to resume: read this file, re-confirm the decisions below still
hold, then either build sub-project 1's existing spec or brainstorm sub-projects
2–4 properly (each needs its own spec + plan, per `superpowers:brainstorming`).

---

## Why this exists

You asked for: better documentation/discoverability, change & deletion
checklists, a full test suite (including edge-case and adversarial tests), and
end-to-end security testing (authn, authz, OWASP, endpoints) — plus CI gates for
app/security/deployment/migration.

That's four independent subsystems, not one project. Brainstorming surfaced the
same conclusion the security audit did: **there is no second reviewer** (249 of
252 commits are one author), so every rule in any of this only holds if it's
enforced by a test or a CI gate, not by a checklist someone is trusted to follow.

## Decisions already made (re-confirm before resuming — may go stale)

| Decision | Choice | Why |
|---|---|---|
| Primary audience | AI agents first, maintainer second | Solo dev working heavily through agents; docs need to be greppable/loadable, not just readable |
| Enforcement model | Tiered — fast local (pre-commit, <5s), blocking on PR (<5min), advisory nightly | A solo dev given 10 blocking gates starts using `--no-verify` |
| "Anti-tests" scope | Negative tests (assert forbidden things fail) + abuse-case tests (attacker-goal scenarios). **Not** mutation testing, **not** fuzzing — both explicitly declined as out of scope | Keeps everything fast enough to run in normal CI |
| E2E security target | Two tiers: in-process (httpx/ASGI) on every PR + live Docker stack nightly | ~1/3 of the audit findings live in Caddy/nginx/compose config that in-process tests can't see |
| Sequencing | Spine (CI+tooling) → Security assurance → Navigability → DevSecOps | Audit fixes are about to land on security-critical code with zero CI; build the net before the high-wire act, not after |
| CI host | GitHub Actions (`origin` remote) | Richest ecosystem for gitleaks/trivy/pip-audit, 2000 free min/month covers this workload |
| Branch flow | PR required to `main`, CI must pass | Only way the gate is real with no second reviewer — the PR diff is the closest thing to a review |

## The one mechanism everything else hangs off

**The invariant registry.** Every security or architectural rule gets an ID
(`INV-001`, `INV-002`, ...), one sentence, and *exactly one test*.
`docs/INVARIANTS.md` is the table; `@pytest.mark.invariant("INV-xxx")` marks the
enforcing test; a bidirectional CI check fails if a row has no matching test or
a test claims an ID with no row. This generalises what
`unit_tests/test_compose_exposure.py` and
`unit_tests/test_dockerignore_covers_secrets.py` already do by hand.

Docs cite `INV-xxx` instead of restating the rule, so prose can't drift from
behaviour — which is how `docs/TECHNICAL_REFERENCE.md` grew to 94 KB and stopped
being trustworthy.

Every finding in `docs/SECURITY_AUDIT_2026-09-01.md` (KUB-001 … KUB-019, plus
the 21 low-severity ones) converts directly into an invariant + regression test
once it's fixed. That conversion **is** most of sub-project 2's content.

---

## Sub-project 1 — The enforcement spine (SPEC EXISTS, NOT BUILT)

Full spec: `docs/superpowers/specs/2026-09-01-maintainability-spine-design.md`
(486 lines, self-reviewed, ready for a plan). Summary:

- `justfile` with three tiers: `just fast` (pre-commit), `just check` (PR gate),
  `just deep` (nightly, stub for now).
- Ruff (lint+format, one tool) as a hard gate; mypy advisory-only, scoped to
  `app/services/` only — deliberately not promised as full coverage.
- Test taxonomy via pytest markers (`invariant`, `negative`, `abuse`, `edge`,
  `slow`) layered onto the existing `tests/` + `unit_tests/` split — no renaming.
- The invariant registry mechanism (above), seeded with 3 invariants.
- Migration safety checks in CI: single head, no model/DB drift, upgrade→downgrade→upgrade round trip.
- GitHub Actions: 4 parallel jobs (lint, unit, integration, frontend), gitleaks
  secret scanning as a hard gate, nightly stub workflow.
- Pre-commit: ruff, gitleaks, large-file check — nothing slower than 5s.
- Root `AGENTS.md`, under 150 lines, commands + taxonomy + the invariant rule +
  a hazards list (KEK rotation, non-idempotent migrations, override file, etc).

**Next step when resumed:** run this spec through `superpowers:writing-plans`,
then execute. Nothing here has been built — no `justfile`, no CI, no
`AGENTS.md`, no `INVARIANTS.md` exist yet in the tree.

---

## Sub-project 2 — Security assurance (NOT SPEC'D — sketch only)

Turns `docs/SECURITY_AUDIT_2026-09-01.md` into permanent, CI-enforced tests. This
is where most of the "anti-test suite" and "OWASP / authn / authz / endpoint
testing" request actually gets built.

**Rough shape, to refine when this gets brainstormed properly:**

- **Authorization matrix as code.** The audit's Appendix A/C.4 script (walks
  `app/main.py`'s FastAPI routes and resolves each dependency chain) becomes a
  permanent test fixture: `tests/security/test_authz_matrix.py`. Every endpoint's
  expected guard (module/role/none/internal-key) is declared in a table; the test
  fails if reality drifts from the table. This is what would have caught KUB-001
  and KUB-019 the day they were introduced, not months later in an audit.
- **Negative tests, one per capability.** For every role/module boundary: the
  forbidden case must 403, not 200 and not 500. Paired with every existing
  "happy path" test where practical, per your "negative tests" answer.
- **Abuse-case tests, one per audit finding.** Each of KUB-001 through KUB-019
  (and the relevant low-severity ones) becomes a permanent test written from the
  attacker's side — "claim an auditor invite for an email I don't own", "read a
  document outside my bucket", "reopen a closed financial year as an employee".
  These are regression tests for the fixes about to be made; they must keep
  failing to exploit forever.
- **The ~30 regression tests already specified inline in the audit itself** — go
  back through `docs/SECURITY_AUDIT_2026-09-01.md` §4 findings, each has a
  "Regression test" subsection with actual pytest code. These are pre-written;
  sub-project 2 is largely wiring them in as the fixes land, not designing them.
- **OWASP coverage mapping.** A table (OWASP Top 10 category → which invariant/test
  covers it → which finding, if any, it was born from) so "did we check X" has an
  answer instead of requiring another full audit.
- **Two-tier E2E** (per your decision): `tests/security/` in-process against the
  ASGI app for authn/authz/injection/endpoint conformance on every PR; a
  `docker compose up` based suite for edge-layer things (security headers,
  gateway routing rules, XFF trust boundary, exposure checks reusing
  `ops/kubera-verify-exposure.sh`) that runs nightly via the `just deep` stub
  from sub-project 1.
- **Coverage ratchet** (mentioned in sub-project 1's spec, belongs to this one to
  actually turn on): coverage must not *decrease* on `app/auth.py`,
  `app/routers/auth.py`, `app/services/` — not a threshold, a ratchet.

**Open questions for when this gets brainstormed:**
- Does the authz-matrix test replace or supplement the introspection script from
  the audit's Appendix C.4, and where does it live long-term?
- Should abuse-case tests be organized by KUB-id (traceable to the audit) or by
  OWASP category (traceable to a standard)? Possibly both, via tags.
- How much of `docker compose up`-based nightly E2E is worth building vs. just
  running `ops/kubera-verify-exposure.sh` in CI (the audit flagged this as
  port-exposure-only, not headers/routing/auth boundaries — is that gap worth
  closing now or later?).

---

## Sub-project 3 — Navigability (NOT SPEC'D — sketch only)

Makes the codebase easy to find your way around, for an agent walking in cold.

**Rough shape:**

- Per-directory `AGENTS.md` files (`app/routers/AGENTS.md`, `app/services/AGENTS.md`,
  etc.) — short, pointing at conventions and gotchas specific to that directory.
  Root `AGENTS.md` (sub-project 1) stays the 30-second orientation; these are the
  next layer down.
- A docstring convention, enforced where practical. Observed during the audit:
  `app/services/*.py` already has genuinely good module docstrings (see
  `document_access.py`, `auditor_access.py`); `app/routers/*.py` and
  `app/models/*.py` have essentially none. This is the gap to close, following the
  services pattern rather than inventing a new one.
- Restructure or regenerate `docs/TECHNICAL_REFERENCE.md` (94 KB, 18 sections) so
  it doesn't silently rot. Options to weigh: split into per-topic files that stay
  small enough for an agent to load individually; generate parts of it
  mechanically (e.g. the API reference section, the data-model section) from the
  code instead of hand-maintaining prose that drifts; or keep it but have the
  invariant registry (sub-project 1) be the source of truth for anything
  behavioral, with the reference doc only covering things that don't change
  often (architecture, not current endpoint lists).
- Decide what to do with the stale docs already in `docs/`:
  `auditease_net_loss_bug_log.md`, `company-onboarding-plan.md`,
  `handoff_auditease_slice3.md`, and the 104 KB generated
  `technical-reference.html` — archive, delete, or fold into the restructure.
- ADRs for the decisions worth preserving the *why* of (e.g. Bearer+localStorage
  over cookies — see the audit's §6.1 — envelope encryption key hierarchy,
  hard-delete vs. soft-delete company purge).
- A generated "docs map" — something that lists what documentation exists and
  what it covers, so an agent (or you) can find the right doc instead of grepping
  four overlapping references.

**Open questions:**
- Full rewrite of `TECHNICAL_REFERENCE.md` or incremental split? A full rewrite
  risks losing detail that's actually still accurate; incremental splitting risks
  never finishing.
- Is docstring coverage worth a CI gate (e.g. every public router function needs
  one) or advisory-only, like mypy in sub-project 1?

---

## Sub-project 4 — DevSecOps / operational hardening (NOT SPEC'D — sketch only)

Everything that needs the live stack or external scanning, plus the
checklist-as-skill idea.

**Rough shape:**

- **Container/dependency scanning**, nightly, advisory (never blocks a PR, per
  the tiered-enforcement decision): `trivy` against the built `api`, `worker`,
  `gateway`, `frontend` images; `pip-audit` (or `uv`'s equivalent) against
  `uv.lock`; `npm audit` against `frontend/package-lock.json`. Findings open
  issues, not failures.
- **Live-stack nightly E2E** — the other half of sub-project 2's two-tier E2E
  decision. `docker compose up` the real stack, probe through Caddy → gateway,
  assert security headers, edge routing rules (marketing vs. app domain
  separation in `gateway/modes/app.conf`), rate-limit behavior, and exposure
  (building on `ops/kubera-verify-exposure.sh`).
- **Checklists as skills, not documents.** The brainstorm's key insight: a
  `docs/CHECKLIST_DELETING_CODE.md` won't get read by an agent starting that kind
  of work; the same checklist as a project-local skill under `.claude/skills/`
  gets loaded automatically when relevant. Candidates for checklist-skills:
  - deleting a table/column/model (given the cascade complexity documented in
    `account_admin.purge_company`'s own docstring)
  - adding a new API endpoint (must declare its module gate — ties directly to
    the sub-project 2/KUB-001 fix, so this becomes the mechanism that prevents
    that class of bug recurring)
  - adding a new Alembic migration (idempotency, transaction safety, matches the
    CI checks from sub-project 1 §6)
  - rotating a secret (`ROOT_MASTER_KEK`, `JWT_SECRET_KEY`, `INTERNAL_API_KEY`) —
    partially documented already in `SECURITY_HARDENING.md` §6, could become a
    proper checklist-skill
  - deploying / migrating a server — `ops/kubera-migrate.sh` and friends already
    do a lot of this; the checklist-skill would be the human-facing companion
- **Alerting on the things the audit found silent**: nightly backup failures
  (KUB-015), rate-limiter fail-open (KUB-014), internal-key usage (KUB-012) —
  these need somewhere to actually notify, which doesn't exist yet.

**Open questions:**
- What's the actual notification channel (email via the existing SMTP
  infrastructure? something else)? Nothing currently exists to alert *anyone* to
  a silent failure.
- Scope of the checklist-skill set — start with the 5 above, or fewer to avoid
  building skills nobody ends up using?

---

## Explicitly rejected during brainstorming (don't re-litigate without new info)

- Mutation testing (mutmut/cosmic-ray) — real value, but slow and adds a tool
  category; declined in favor of negative + abuse-case tests only.
- Property/fuzz testing (Hypothesis) — same reasoning.
- Renaming `tests/` → `tests/integration/` and `unit_tests/` → `tests/unit/` —
  churn without benefit; pytest markers layer the taxonomy on top instead.
- Coverage percentage *thresholds* as a hard gate — rewards trivial tests; the
  invariant registry is the real correctness signal. (The narrower
  non-decrease *ratchet* on security-critical files is kept — see sub-project 1.)
- "Everything blocks, no exceptions" enforcement model — unrealistic once
  container scanning and full E2E are in the picture (minutes, not seconds).
- Advisory-only enforcement (report but never block) — rejected for a
  compliance product handling tenant financial data.

---

## Where to pick this back up

1. Re-read this file and `docs/SECURITY_AUDIT_2026-09-01.md`'s remediation
   roadmap (§7) — confirm the sequencing still makes sense once the security
   fixes are actually done (some may change what sub-project 2 needs).
2. Sub-project 1 already has a full spec — go straight to
   `superpowers:writing-plans` for it, no brainstorming needed, unless something
   about the codebase changed enough to invalidate the spec's assumptions.
3. Sub-projects 2–4 each need a proper `superpowers:brainstorming` session before
   they're buildable — the sketches above are starting points, not designs.
