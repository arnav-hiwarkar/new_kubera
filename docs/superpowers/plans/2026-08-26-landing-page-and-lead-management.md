# Kubera Marketing Landing Page & Secure Lead Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a modern, animated marketing landing page for `kuberacompliance.com` inspired by the corporate compliance brochure, a hardened lead-capture mechanism (email-only with anti-bot honeypot and strict rate limiting), a stealth Owner Management portal (`/internal/owner-vault` + `list_leads.py`) for manual company provisioning, and multi-domain Caddy routing.

**Architecture:**
- **Frontend:** React + Tailwind + Lucide SPA serving the animated Landing Page on `kuberacompliance.com`, Core App on `app.kuberacompliance.com`, and Stealth Owner Portal on `/internal/owner-vault`.
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL + Redis. Public `POST /api/v1/leads/interest` with honeypot & sliding-window rate limit, protected `GET/POST /api/v1/owner/leads` guarded by `X-Internal-API-Key`.
- **Infrastructure:** Caddy auto-TLS for `DOMAIN` (`app.kuberacompliance.com`) and `LANDING_DOMAIN` (`kuberacompliance.com`).
Spec: `docs/superpowers/specs/2026-08-26-landing-page-and-lead-management-design.md`.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Lucide React, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL 16, Redis 7, Caddy 2.

---

### Task 1: Database Model & Migration for Leads

**Files:**
- Create: `app/models/lead.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/a4b5c6d7e8f9_add_leads_table.py`
- Test: `tests/test_lead_model.py`

**Objectives:**
- Define `Lead` SQLAlchemy model with UUID primary key, email, company_name, phone, entities_count, notes, status (`new`, `contacted`, `converted`, `archived`), ip_address, user_agent, created_at, updated_at.
- Index email, status, and created_at.
- Run Alembic migration to update schema.

- [x] **Step 1: Write model test in `tests/test_lead_model.py`**
- [x] **Step 2: Create `app/models/lead.py` and register in `app/models/__init__.py`**
- [x] **Step 3: Create Alembic migration revision**
- [x] **Step 4: Run tests with `.venv/bin/pytest tests/test_lead_model.py -v`**
- [x] **Step 5: Commit changes**

---

### Task 2: Public Lead Capture Endpoint with Hardened Security

**Files:**
- Create: `app/schemas/lead.py`
- Create: `app/routers/leads.py`
- Modify: `app/main.py`
- Test: `tests/test_leads_api.py`

**Objectives:**
- Implement `POST /api/v1/leads/interest`:
  - `website_url_hp` honeypot check (silently succeeds without DB write if filled).
  - Redis sliding-window rate limiter (3 requests / 10 min per IP/email).
  - Input normalization (lowercase, stripped email, length limits).
  - Generic anti-enumeration response payload.
  - Parameterized ORM write.
- Register router in `app/main.py`.

- [x] **Step 1: Write API tests in `tests/test_leads_api.py` (testing rate limits, honeypot, validation, anti-enumeration)**
- [x] **Step 2: Implement schemas in `app/schemas/lead.py`**
- [x] **Step 3: Implement endpoints in `app/routers/leads.py` and include in `app/main.py`**
- [x] **Step 4: Run tests with `.venv/bin/pytest tests/test_leads_api.py -v`**
- [x] **Step 5: Commit changes**

---

### Task 3: Stealth Owner Lead Management API & Server CLI

**Files:**
- Modify: `app/routers/leads.py`
- Create: `list_leads.py`
- Test: `tests/test_owner_leads.py`

**Objectives:**
- Add owner routes in `app/routers/leads.py` guarded by `X-Internal-API-Key`:
  - `GET /api/v1/owner/leads`: List leads with status filter.
  - `PATCH /api/v1/owner/leads/{id}/status`: Update lead status.
  - `POST /api/v1/owner/leads/{id}/provision`: Initialize company, create per-company KEK, mint 48h activation key, mark lead `converted`, return activation link.
- Create standalone operator CLI `list_leads.py`.

- [x] **Step 1: Write tests in `tests/test_owner_leads.py`**
- [x] **Step 2: Implement owner endpoints in `app/routers/leads.py`**
- [x] **Step 3: Create `list_leads.py` operator CLI script**
- [x] **Step 4: Run tests with `.venv/bin/pytest tests/test_owner_leads.py -v`**
- [x] **Step 5: Commit changes**

---

### Task 4: Marketing Landing Page Component & Micro-Animations

**Files:**
- Create: `frontend/src/pages/landing/LandingPage.tsx`
- Create: `frontend/src/pages/landing/components/LandingHeader.tsx`
- Create: `frontend/src/pages/landing/components/LandingHero.tsx`
- Create: `frontend/src/pages/landing/components/ProblemVsKubera.tsx`
- Create: `frontend/src/pages/landing/components/ModuleShowcase.tsx`
- Create: `frontend/src/pages/landing/components/WhyItPaysOff.tsx`
- Create: `frontend/src/pages/landing/components/PricingSection.tsx`
- Create: `frontend/src/pages/landing/components/LandingFooter.tsx`
- Create: `frontend/src/pages/landing/components/LeadModal.tsx`
- Test: `frontend/src/pages/landing/LandingPage.test.tsx`

**Objectives:**
- Implement the modern enterprise light/dark hybrid landing page with content from brochure.
- Build interactive module tab switcher (docVault, Asset Life Cycle, AuditEase, PMO / CEO Office, Kubera.ai teaser).
- Build pricing cards (Standard, Pro, Enterprise) and comparison matrix.
- Build single-field email capture and lead modal with loading states and micro-interactions.
- Add "Go to App / Log In" CTA buttons.

- [x] **Step 1: Write frontend component tests in `LandingPage.test.tsx`**
- [x] **Step 2: Implement Landing Page components and micro-animations**
- [x] **Step 3: Run frontend tests**
- [x] **Step 4: Commit changes**

---

### Task 5: Stealth Owner Portal Web View

**Files:**
- Create: `frontend/src/pages/owner/OwnerLeadsPage.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Test: `frontend/src/pages/owner/OwnerLeadsPage.test.tsx`

**Objectives:**
- Create `/internal/owner-vault` route protected by `INTERNAL_API_KEY` prompt.
- Display real-time leads table with status badges, search, and "Provision Company" modal.
- Ensure route is unlinked from public menus, headers, and footer.

- [x] **Step 1: Write test for OwnerLeadsPage**
- [x] **Step 2: Implement `OwnerLeadsPage.tsx` and configure route in `frontend/src/routes/index.tsx`**
- [x] **Step 3: Run frontend tests**
- [x] **Step 4: Commit changes**

---

### Task 6: Multi-Domain Caddy & Gateway Configuration

**Files:**
- Modify: `Caddyfile`
- Modify: `.env.example`
- Modify: `frontend/src/routes/index.tsx` (hostname-based route dispatching)

**Objectives:**
- Update `Caddyfile` to support both `{$DOMAIN}` and `{$LANDING_DOMAIN}`.
- Configure hostname detection so `kuberacompliance.com` renders the landing page and `app.kuberacompliance.com` navigates to app login.
- Support direct `/landing` path across any domain for testing.

- [x] **Step 1: Update `Caddyfile` and `.env.example`**
- [x] **Step 2: Update router dispatch logic in `frontend/src/routes/index.tsx`**
- [x] **Step 3: Run full backend and frontend test suites**
- [x] **Step 4: Commit and push changes to GitHub**
