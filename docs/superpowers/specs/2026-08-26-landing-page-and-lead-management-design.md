# Kubera Marketing Landing Page & Secure Lead Management — Design Specification

**Date:** 2026-08-26  
**Status:** Approved (Pending Implementation Plan)  

---

## 1. Context & Objectives

Kubera is a SaaS compliance and statutory records treasury built for SMEs and multi-company groups. Currently, the entire stack serves the core application under `app.kuberacompliance.com`. 

We are adding:
1. A **modern, aesthetic marketing landing page** served at `kuberacompliance.com` (and `www.kuberacompliance.com`), inspired by the Kubera Corporate Compliance brochure, with clean enterprise light/dark hybrid styling and micro-animations.
2. A **minimal, secure lead capture mechanism** where interested companies can submit their email address to request access or a demonstration.
3. A **stealth Owner Lead Management portal** (`/internal/owner-vault`) and CLI tool (`list_leads.py`) allowing the Kubera owner to track incoming interest, update lead status, and manually provision company accounts and one-shot activation keys (the public website never auto-provisions logins).
4. **Hardened security & DoS/SQLi protections**: Anti-spam honeypot, Redis-backed sliding-window rate limiting, input normalization, parameterization, and constant-time API key verification.
5. **Multi-domain Caddy routing**: Dual-domain configuration via `.env` (`DOMAIN=app.kuberacompliance.com` and `LANDING_DOMAIN=kuberacompliance.com`) with automatic Let's Encrypt TLS certificates.

---

## 2. System Architecture & Routing

```
                                  Internet
                                     │
                     ┌───────────────┴───────────────┐
                     │                               │
        https://kuberacompliance.com    https://app.kuberacompliance.com
                     │                               │
                     ▼                               ▼
       ┌───────────────────────────────────────────────────────────┐
       │                   Caddy Reverse Proxy                     │
       │           (Auto TLS for DOMAIN & LANDING_DOMAIN)          │
       └─────────────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
       ┌───────────────────────────────────────────────────────────┐
       │                       Nginx Gateway                       │
       └──────────────┬─────────────────────────────┬──────────────┘
                      │                             │
        /api/v1/leads │                             │ Static Assets / SPA Routes
                      ▼                             ▼
       ┌─────────────────────────────┐┌────────────────────────────┐
       │       FastAPI Backend       ││      Vite React Client     │
       │   - Lead Capture Endpoint   ││  - Landing Page Component  │
       │   - Owner Management API    ││  - Core Kubera App Routes  │
       │   - Company Provisioning    ││  - Stealth Owner Portal    │
       └──────────────┬──────────────┘└────────────────────────────┘
                      │
                      ▼
       ┌─────────────────────────────┐
       │      PostgreSQL & Redis     │
       │   - leads Table             │
       │   - Rate Limit Key Storage  │
       └─────────────────────────────┘
```

### Domain Routing Matrix:
- **`kuberacompliance.com` / `/`**: Serves the Marketing Landing Page with direct links to `https://app.kuberacompliance.com/login`.
- **`app.kuberacompliance.com` / `/`**: Automatically navigates to the App login/dashboard (`/login` or `/app`).
- **`/landing`**: Always explicitly renders the Landing Page across any domain for testing/previewing.
- **`/internal/owner-vault`**: Stealth Owner Dashboard, unlinked from public menus, requiring `INTERNAL_API_KEY` verification.

---

## 3. Public Lead Capture Security & API Design

### 3.1 Endpoint: `POST /api/v1/leads/interest`
Public, unauthenticated lead submission for interested companies.

**Request Schema (`LeadInterestRequest`)**:
```python
class LeadInterestRequest(BaseModel):
    email: EmailStr  # normalized, max 100 chars
    company_name: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=30)
    entities_count: Optional[int] = Field(None, ge=1, le=100)
    notes: Optional[str] = Field(None, max_length=1000)
    website_url_hp: Optional[str] = None  # Honeypot field (must be empty)
```

**Security Defenses**:
1. **Honeypot Trap**: If `website_url_hp` is filled (by automated bot scrapers), the request returns `200 OK` immediately without writing to the database.
2. **Strict Sliding-Window Rate Limiting**: Max 3 requests per IP / email per 10-minute window stored in Redis (`ratelimit:lead:{ip}`). Exceeding limits returns `429 Too Many Requests`.
3. **Anti-Enumeration / Timing Attack Defense**: Always returns an identical generic response:
   ```json
   {
     "status": "received",
     "message": "Thank you for your interest in Kubera. Our team will contact you shortly."
   }
   ```
4. **Input Sanitization**: Email is stripped, lowercased, validated via `email-validator`, and escaped.
5. **SQL Injection Defense**: 100% parameterized SQLAlchemy ORM queries; no raw string interpolation.

---

## 4. Database Schema: `leads` Table

New table managed via Alembic:

```sql
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    phone VARCHAR(50),
    entities_count INTEGER,
    notes TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'new', -- 'new', 'contacted', 'converted', 'archived'
    ip_address VARCHAR(100),
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_leads_email ON leads(lower(email));
CREATE INDEX ix_leads_status ON leads(status);
CREATE INDEX ix_leads_created_at ON leads(created_at DESC);
```

---

## 5. Stealth Owner Portal & CLI Tooling

### 5.1 Owner Endpoints (Protected by `X-Internal-API-Key`)
1. `GET /api/v1/owner/leads`: Returns list of all leads with filtering by status and pagination.
2. `PATCH /api/v1/owner/leads/{id}/status`: Updates lead status (`contacted`, `converted`, `archived`).
3. `POST /api/v1/owner/leads/{id}/provision`:
   - Provisions a new `Company` and pending admin `CompanyUser` using the lead details.
   - Generates per-company KEK and mints a 48h one-shot activation key.
   - Automatically marks lead status as `converted`.
   - Returns the one-shot activation link directly to the owner.

### 5.2 Server CLI Tool: `list_leads.py`
A standalone operator tool on the server:
```bash
python3 list_leads.py                  # List all leads and status
python3 list_leads.py --status new     # Filter new inquiries
```

### 5.3 Stealth Web View: `/internal/owner-vault`
- Clean, minimal UI with a dark security theme.
- Password/Key prompt requesting `INTERNAL_API_KEY` (saved in session storage).
- Real-time table of leads with status badges, entity counts, notes, and a **"Provision Company"** button that generates onboarding credentials with one click.

---

## 6. Landing Page Frontend UI & Content

### 6.1 Theme & Aesthetics
- **Style**: Modern enterprise light/dark hybrid with deep indigo-slate palette (`#0B0F19`, `#1E293B`, `#4F46E5`, `#6366F1`, crisp `#FFFFFF` surfaces, subtle border gradients).
- **Micro-Animations**:
  - Hero floating badge with subtle pulse.
  - Interactive email input with focus glow and button transition.
  - Hover elevation and border illumination on cards.
  - Smooth tab switching for the "Four Modules, One Vault" showcase.
  - Responsive mobile-friendly navigation.

### 6.2 Page Sections (Direct from Brochure Content)
1. **Top Header**: Logo + ETHDC credit, Links (*Modules*, *Value*, *Pricing*), Primary Button (*Go to App / Log In*).
2. **Hero Section**:
   - Badge: *SaaS · Built for SMEs & Multi-Company Groups*
   - Headline: *"A secure treasury for the records that keep your company compliant, audit-ready, and continuous."*
   - Subhead: *"Compliance shouldn't live in someone's inbox. Governance, statutory repositories, dual-regime asset depreciation, and scoped auditor access in one access-controlled system."*
   - Minimalist Email Input CTA + "Request Access".
3. **Problem vs. Kubera Comparison Matrix**:
   - Inboxes & scattered chasing vs. Centralized access-controlled buckets.
   - Lost institutional memory on resignation vs. Permanent institutional continuity.
   - Drifting formats across hires vs. Standardized compliance workflows.
4. **"Four Modules, One Vault" Interactive Showcase**:
   - **Module 01: Repository Management (docVault)**: Secretarial, ROC, GST & Tax, HR, Legal, Banking & Finance.
   - **Module 02: Asset Life Cycle**: Fixed Asset Register, capitalisation to disposal, dual Companies Act & IT Act depreciation runs.
   - **Module 03: Audit Management (AuditEase)**: Multi-cycle trial balance import, scoped auditor access, query tracking, tamper-evident logs.
   - **Module 04: PMO / CEO Office**: Market segments, partner registry, client directory, KRA tracking, collection projections.
   - **Teaser Badge**: *Kubera.ai — Intelligence layer launching Feb 2027*.
5. **"Why It Pays Off" (6-Pillar Value Grid)**:
   - Always audit-ready, Lower key-person risk, Faster reviews, Confidential by design, Standardised, Scales with you.
6. **Membership & Pricing**:
   - **Standard** (₹60,000 / year — up to 2 entities)
   - **Pro** (₹100,000 / year — up to 4 entities — *Most Popular*)
   - **Enterprise** (Custom / Tailored — 5+ entities, white-labelled)
   - Clear terms: SaaS subscription, 50% advance / 50% within 3 months.
7. **Footer**: Quick links, compliance disclosure, and direct link to app.

---

## 7. Testing & Verification

1. **Unit & API Tests (`tests/test_leads.py`)**:
   - Public lead submission with valid email passes and returns generic response.
   - Honeypot trap triggers silent rejection when filled.
   - Rate limiting triggers HTTP 429 when threshold exceeded.
   - Invalid email formats return HTTP 422.
   - Owner lead endpoints reject missing or invalid `X-Internal-API-Key` with HTTP 403.
   - Owner lead provisioning creates company, sets per-company KEK, mints activation key, and updates status to `converted`.
2. **Frontend Component Tests (`frontend/src/pages/landing/LandingPage.test.tsx`)**:
   - Renders all brochure sections, pricing cards, and interactive tabs.
   - Form submission validates email and shows success message.
3. **E2E / Multi-Domain Routing Verification**:
   - Verify Caddy routes `kuberacompliance.com` to landing page and `app.kuberacompliance.com` to app login.
