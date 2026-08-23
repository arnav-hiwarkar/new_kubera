# Handoff — Calculation Trace Drawer (Kubera assets module)

You are taking over an in-progress feature build. Read this document fully before
touching anything. It tells you what is being built and why, what is already done,
what to do next, how to do it, and the specific traps that have already cost time.

Repo: `/Users/ash/Projects/new_kubera` · Branch: `graph` (NOT main) · Date of handoff: 2026-08-23

---

## 1. What we are building, and why

Kubera is an Indian fixed-asset register and compliance product. Throughout the assets
module it displays derived figures — depreciation for the year, closing carrying amount,
landed cost, recoverable vs. capitalizable GST — with **no way for a user to see how the
number was reached**. When an auditor challenges a figure, the only recourse today is
reading the Python engine source.

We are adding a **"See the calculation" affordance** beside every major derived figure.
It opens a right-side drawer showing, for each step of the computation:

1. the symbolic formula (`Cost − Residual value`)
2. the same formula with this asset's actual values substituted in (`100,000.00 − 5,000.00`)
3. the result (`95,000.00`)

Covered in v1: Companies Act Schedule II per-asset depreciation, Income Tax Act s.32
block depreciation, the acquisition cost build-up, and the GST/ITC split.

Explicitly out of scope in v1: asset reports and register roll-forwards; the disposal
modal (disposal gain/loss appears as steps inside the depreciation trace instead).

### Why it was built the way it was

The engines already computed every interesting intermediate — the Schedule II WDV rate
`1-(s/c)^(1/n)`, the pro-rata active-day fraction, the residual cap, the full-rate and
half-rate tax pools — and then **threw them away**, returning only final figures. So the
first half of this work is making the engines emit their workings, and the second half is
a presentation layer that labels them.

Four decisions the user made during brainstorming, which you must not quietly revisit:

- **Backend trace for depreciation, frontend adapter for costing.** Depreciation math is
  statutory and a finalized run must explain itself with the inputs it actually used, so
  its trace is built server-side and persisted. Acquisition costing already returns every
  intermediate via `CostPreviewResponse`, and has no historical version to reconcile, so
  its trace is assembled in TypeScript.
- **Formula + substitution + result per step**, with statutory citations only on the rules
  that genuinely surprise people (180-day half rate, blocked ITC, residual cap).
- **A right-side drawer**, not a modal or inline expander — a trace is a tall ordered list,
  and one drawer serves both detail cards and table rows.
- **One trigger per calculation block, with step-level deep linking.** Pages stay clean;
  high-traffic figures can still jump straight to their step.
- **Projection when no run exists.** Opening the drawer for an asset with no computed run
  runs the engine in dry-run mode and shows a clearly-badged projection, so the drawer is
  useful during data entry, not only afterwards.

### The invariant that the whole feature rests on

**A trace must never display a number different from the row it explains.** Everything
below exists to enforce that:

- The engines emit raw `intermediates`; a separate builder layer labels and formats them.
  The builders never recompute anything.
- All formatting happens once, at the producer, using the same Decimal quantization the
  engine used. The renderer only lays out text and adds the unit symbol — it never rounds.
- Each trace marks its page-visible figures with `emphasis`, and a test asserts every
  emphasised step's formatted string equals the corresponding persisted line field.
- **Percent-unit coherence:** for any step whose `unit` is `percent`, the substitution read
  as literal arithmetic must produce the displayed result. Schedule II rate formulas yield
  a fraction, so those steps carry an explicit `× 100` term. Money-unit steps express rates
  inline with a `%` sign (`100,000.00 × 5.00%` → `5,000.00`) and are already coherent —
  adding `× 100` to those would be WRONG.
- Where the engine clamps or caps a value, the substitution must show the clamp rather than
  printing arithmetic that reaches a different number.

---

## 2. Authoritative documents

| Document | Path |
|---|---|
| Design spec (approved) | `docs/superpowers/specs/2026-08-23-calculation-trace-drawer-design.md` |
| Implementation plan (15 tasks, full code per task) | `docs/superpowers/plans/2026-08-23-calculation-trace-drawer.md` |
| Progress ledger (source of truth for what is done) | `.superpowers/sdd/2026-08-23-calculation-trace-drawer/progress.md` |
| Per-task briefs and reports | `.superpowers/sdd/2026-08-23-calculation-trace-drawer/task-N-brief.md` / `-report.md` |

**The ledger is the recovery map.** If your context is ever unclear about what is done,
trust `progress.md` and `git log`, not recollection. Tasks with a `Task N: complete` line
are done; do not redo them.

The plan has been patched three times to correct defects found in review (commits `d0cfa4a`,
`dd0a851`). Its current text is correct. Briefs are extracted from it per task.

---

## 3. What is done

All work is committed on branch `graph`. Backend calculation logic is complete.

| # | Task | Status | Commits |
|---|---|---|---|
| 1 | Trace primitives (`CalcStep`, `CalcTrace`, `TraceBuilder`, formatters) | complete | `7b4c139..ef84623` |
| 2 | Schedule II engine emits `intermediates` | complete | `99a7a5b` |
| 3 | Income Tax engine emits `intermediates` | complete | `34c8278` |
| 4 | Schedule II trace builder | complete (2 fix rounds) | `8a60017..286585c` |
| 5 | Income Tax block trace builder | complete (1 fix round) | `f174217..a29c694` |
| 6 | `calc_trace` JSONB column, models, Pydantic schemas | complete | `adb8d39` |
| 7 | Runs persist traces on every line | complete | `95373d6` |
| 8 | Projection endpoint (refactor + `POST /explain`) | complete | `c96e1ff`, `a49658c` |
| 9 | Frontend trace types + acquisition adapter | in progress | — |
| 10–15 | Frontend drawer and wiring | not started | — |

Test baselines at the last clean point:
- `pytest unit_tests/ -q` → **252 passed**
- `pytest tests/test_depreciation_api.py -q` → **33 passed** (must be run solo, see trap 5)
- `cd frontend && npm run test` → **43 files, 197 tests passed**

Alembic head is now `d7a1c9b2e4f3` (`add_calc_trace_to_depreciation_lines`), chaining from
`c1f2e3d4a5b6`. The migration adds a **nullable** `calc_trace` JSONB to
`asset_depreciation_lines` and `it_block_depreciation_lines` with **no backfill** — this is
deliberate. A trace records how a figure was reached with the inputs of the moment;
synthesising one now for a run computed months ago would attach today's inputs to
yesterday's number. Lines without a trace are reported as such in the UI, which offers a
badged projection instead.

### Files created so far

- `app/services/calc_trace.py` — `CalcStep`, `CalcTrace`, `TraceBuilder`, `fmt_money`,
  `fmt_dec`, `fmt_pct`, `fmt_int`. Presentation primitives, no domain knowledge.
- `app/services/calc_trace_builders.py` — `build_schedule_ii_trace`, `build_it_block_trace`,
  operator constants `MUL`/`DIV`/`SUB`/`ADD`, group constants, `SCHEDULE_II_LINE_FIELDS`,
  `IT_BLOCK_LINE_FIELDS`. **All user-facing labels and statutory wording live here and
  nowhere else.**
- `alembic/versions/d7a1c9b2e4f3_add_calc_trace_to_depreciation_lines.py`
- `unit_tests/test_calc_trace.py`, `unit_tests/test_calc_trace_builders.py`

### Files modified so far

- `app/services/depreciation.py` — result carries `intermediates`; `_remaining_life_days`
  now returns `(days, total_life_days, consumed)`.
- `app/services/it_depreciation.py` — result carries `intermediates` incl. `branch`
  (`standard`/`stcg`/`stcl`) and `excess_sales` on the sales-exceed-pool path.
- `app/services/depreciation_query.py` — persists traces; and per Task 8's refactor, now
  exposes `build_asset_depreciation_input`, `build_it_block_input`, `asset_it_contribution`.
- `app/models/depreciation.py`, `app/schemas/depreciation.py` — `calc_trace` column and
  `CalcStepSchema`/`CalcTraceSchema`.

---

## 4. Immediate next action

**The entire backend is done and reviewed clean (Tasks 1–8).** Start at Task 9, or resume
whichever frontend task the ledger shows as incomplete.

Backend surface now available to the frontend:

- `GET /api/v1/depreciation/runs/{run_id}/lines` and `/it-lines` — each line response now
  carries `calc_trace` (nullable). A run computed before this feature has `null` there.
- `POST /api/v1/depreciation/explain` — body `{asset_id, financial_year_id}`, returns
  `{companies_act: CalcTrace, income_tax: CalcTrace | null}`. Both traces have
  `is_projection: true` and `computed_at: null`. Writes nothing. Returns 422 with the
  engine's own message when the asset's inputs are too incomplete to compute — the drawer
  renders that message as an explanation, so surface it, do not swallow it. `income_tax`
  is `null` when the asset has no IT block.
- Trace JSON shape: `{title, basis, steps[], is_projection, computed_at}` where a step is
  `{key, group, label, formula, substitution, result, unit, emphasis, note}`. `formula` and
  `substitution` are empty strings for a plain input rather than a derivation — the renderer
  must omit those lines rather than printing blanks.

## 5. Tasks 9–15 (frontend)

Briefs are already extracted at `task-9-brief.md` … `task-15-brief.md`. Each contains the
complete code. Order matters — later tasks consume earlier interfaces.

| # | Task | Deliverable |
|---|---|---|
| 9 | Trace types + acquisition adapter | `frontend/src/components/calc/types.ts`, `traceFromCostPreview.ts` + tests |
| 10 | The drawer | `CalcStepRow.tsx`, `traceToText.ts`, `CalculationDrawer.tsx`, `index.ts` + tests |
| 11 | Trigger + deep link | `ExplainLink.tsx`; `DerivedRow` gains `onExplain` |
| 12 | Refactor | extract `DepreciationRunCard.tsx` out of the 532-line `DepreciationTab.tsx` |
| 13 | Projection client + hook | `depreciationApi.explain`, `useExplainDepreciation(assetId, fyId, enabled)` |
| 14 | Wire the Depreciation tab | run-card triggers, `DepreciationDerivedCard.tsx`, drawer states |
| 15 | Wire Acquisition + Tax tabs | adapter-driven drawers, then regenerate `schema.d.ts` |

Frontend specifics worth knowing before you start:

- **Money formatting is en-US grouping, two places, no symbol** — `"100,000.00"`. This matches
  the app's existing `formatMoney` (which is `formatSigned`, en-US). The `₹` is added by the
  renderer from the step's `unit`, never baked into a string. The spec's illustrative
  Indian-grouped example is superseded; the plan's Global Constraints say so.
- **`CalcStep`/`CalcTrace` TS types are hand-written** in `components/calc/types.ts`, not taken
  from `schema.d.ts`. Regenerating the schema needs a running backend (`npm run gen:api`), and
  the drawer must not be blocked on that. Task 15 step 5 regenerates it and reconciles.
- **`calc_trace` will not exist in `schema.d.ts`** until that regeneration, so Task 14 reads it
  through a local `type WithTrace = { calc_trace?: CalcTrace | null }` cast. This is deliberate,
  not sloppiness — it is in the brief.
- **The operator constants `MUL`/`DIV`/`SUB`/`ADD` are duplicated** from the Python builders into
  `types.ts` on purpose: a frontend-built trace sits in the same drawer as a backend-built one
  and must read identically.
- Task 14 must add `useItBlockDepreciationLines` and `useExplainDepreciation` to the
  `vi.mock('@/api/hooks/depreciation', ...)` factory in `tabs/reopen.test.tsx`, or that test
  calls `undefined`.
- Task 10's projection banner uses a `status-pending` Tailwind token. If that token does not
  exist, check `frontend/tailwind.config.js` and substitute the project's warning token — the
  banner must be visually distinct, not merely differently worded.

Three drawer states Task 14 must keep distinct, because conflating them is how a drawer misleads:

| State | What the drawer shows |
|---|---|
| Line with a trace | The recorded trace, with `computed_at` and the run status |
| No line for this year | A projection, fetched automatically, banner-marked |
| Line without a trace (pre-feature run) | "Recorded before calculation traces were kept", with a button offering a projection — never a silent substitution |

---

## 6. How to execute (the process in use)

We are using `superpowers:subagent-driven-development`: one fresh implementer subagent per
task, a task review after each, and one broad whole-branch review at the end. Do not
implement tasks yourself in the controller session — your context stays for coordination.

Skill scripts live at
`/Users/ash/.claude/plugins/cache/superpowers-marketplace/superpowers/6.2.0/skills/subagent-driven-development/scripts/`.

Per task:

```bash
SKILL=/Users/ash/.claude/plugins/cache/superpowers-marketplace/superpowers/6.2.0/skills/subagent-driven-development
PLAN=docs/superpowers/plans/2026-08-23-calculation-trace-drawer.md

# 1. record BASE before dispatching
git rev-parse HEAD

# 2. extract the brief (already done for tasks 9-15)
$SKILL/scripts/task-brief $PLAN N

# 3. dispatch an implementer with: one line of project context, the brief path
#    ("read this first — it is your requirements, use its exact values verbatim"),
#    interfaces from earlier tasks the brief cannot know, the global constraints,
#    and a report-file path. Never paste accumulated session history.

# 4. after it reports DONE, build the review package and dispatch a task reviewer
$SKILL/scripts/review-package $PLAN <BASE> <HEAD>
```

Review rules that have mattered:

- Hand reviewers **file paths**, never pasted diffs — that is what keeps controller context low
  (still ~15M free after 20 subagent runs).
- Require **two verdicts**: spec compliance (✅/❌) and task quality (findings by severity).
- **Never pre-judge.** Do not tell a reviewer what not to flag. Adjudicate afterwards.
- Critical/Important findings enter a fix loop (max 5 rounds): resume the original implementer
  for rounds 1–3, dispatch a fresh one on a stronger model for 4–5. Each round ends with a
  **scoped** re-review over the fix diff only.
- Minor findings go to the ledger as deferred, for the final review to triage.
- Append a ledger line after every round and every completion.

Model selection: cheapest tier when the brief contains the complete code (transcription plus
testing); mid-tier for surgical edits to existing files and for reviewers; strongest tier for
the final whole-branch review.

**Parallelism:** never run two implementers at once. A reviewer may run alongside an
implementer if they touch different files — but see the Postgres warning below.

---

## 7. Traps already paid for. Do not rediscover these.

1. **The plan's own code has been the defect source, not the implementers.** Every finding so
   far was a bug in the plan's prescribed code, faithfully transcribed. Treat remaining plan
   code blocks with suspicion, especially Task 10's renderer, which must display strings
   without reformatting them.
2. **Percent-unit incoherence appeared twice** (`effective_rate_pct`, `wdv_rate`) — formula
   yielding a fraction while the step displayed a percentage. It is now a stated Global
   Constraint. Check both directions: no incoherent percent step, and no over-correction on
   money steps that legitimately carry `%` inline.
3. **Clamps must be visible.** `remaining_full_pool` printed `100,000.00 − 120,000.00` beside a
   clamped result of `0.00`. `closing_wdv` has the same shape but is deliberately left alone —
   unreachable at realistic rates, and flooring language on a step that never floors is noise.
   That ruling is in the ledger; the final review may overturn it.
4. **No arithmetic in the builders.** An agent "fixed" a problem by computing
   `excess_sales = realized_from_sales − full_pool` in the builder. The fix was to expose
   `excess_sales` from the engine's intermediates. If you need a derived value, expose it from
   the engine; never re-derive it in the presentation layer.
5. **One Postgres, one DB agent.** Concurrent agents hitting the shared Postgres produce
   `DeadlockDetectedError` on `DROP TABLE` at teardown and login failures in unrelated modules
   (`test_health`, `test_maintenance`). These are not code bugs. Fix: `pkill -f pytest`, wait,
   re-run. Run a full `pytest -q` solo. Bring the DB up with
   `docker compose up -d postgres redis`.
6. **Agents die.** Three consecutive failures on one Task 5 agent (two machine sleeps, one 600s
   stall) cost ~120k tokens. Always check `git status` / `git diff` after a failure — partial
   uncommitted work often survives and is worth keeping. Tell implementers to commit
   incrementally, and never to launch a long test run in the background and wait on it.
7. **Do not skip the review even when a diff is byte-identical to the brief.** Task 4's
   Critical was in code that matched the brief exactly.

---

## 8. Definition of done

- Tasks 8–15 complete, each with a clean task review or findings parked with written rulings.
- `pytest -q` green (solo run), `cd frontend && npm run test` green (≥197 tests),
  `npx tsc -b --noEmit` and `npm run lint` clean.
- `npm run gen:api` run against a live backend and `schema.d.ts` committed.
- The plan's **Manual verification** section (its last section) walked by hand — in particular:
  a recorded trace's emphasised figure matching its tile exactly; a stat-tile deep link landing
  ring-highlighted on the right step; the projection banner appearing for a year with no run;
  a 422 rendering as an explanation rather than an error toast; "Copy calculation" producing
  usable plain text; and the drawer checked in both light and dark theme.
- Final whole-branch review dispatched on the strongest available model, pointed at the
  ledger's deferred-minor and parked lines so it can triage what must be fixed before merge:
  `$SKILL/scripts/review-package $PLAN $(git merge-base main HEAD) HEAD`
- Then `rm -rf .superpowers/sdd/2026-08-23-calculation-trace-drawer` and use
  `superpowers:finishing-a-development-branch`.

## 9. Open items carried forward

- `test_intermediates_are_internally_consistent_part_year`'s `min()` assertion is effectively
  tautological and its inputs never exercise the cap branch. Pre-existing cap tests do cover
  the arithmetic.
- `test_calc_step_is_frozen` catches a bare `Exception` rather than `FrozenInstanceError`.
- The "excess spills past the half-rate pool too" sub-branch in the IT builder has no
  formula+substitution+result pinning test.
- `closing_wdv`'s clamp is unreflected in its substitution (deliberate ruling, see trap 3).
- `wdv_rate`/`carrying_for_calc` are nested under `useful_years > 0` as well as the WDV branch,
  so a WDV asset with `useful_life_months <= 0` would lack them. Unreachable today (Pydantic
  `ge=1` at every entry point).
