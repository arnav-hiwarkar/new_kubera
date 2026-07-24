# Kubera Platform — Technology & Tooling Overview

*Prepared for: Management review · Date: 23 July 2026*

Kubera is a **multi-tenant audit and corporate-compliance platform**. This document
sets out every technology, framework, and tool the product is built on — grouped by
layer, with a plain-language note on what each one does and why it was chosen.

**Stack at a glance:** FastAPI · React · PostgreSQL · Redis · Celery · Docker

---

## 1. Runtime architecture

The product ships as a set of containerised services orchestrated together. Each
service has a single responsibility, so the platform can be scaled, monitored, and
recovered piece by piece.

| Service    | Responsibility                                                                              | Port      |
|------------|---------------------------------------------------------------------------------------------|-----------|
| `caddy`    | Public entry point — reverse proxy with automatic HTTPS certificates.                       | 80 · 443  |
| `frontend` | The compiled React application, served as static files by Nginx.                            | internal  |
| `api`      | The FastAPI application — all business logic and API endpoints; runs migrations on start-up.| 8000      |
| `worker`   | Celery worker — runs background jobs (exports, backups) off the request path.               | —         |
| `beat`     | Celery scheduler — triggers timed jobs such as the nightly backup.                          | —         |
| `postgres` | PostgreSQL 16 — the system of record for all application data.                              | 5433      |
| `redis`    | Redis — task queue for Celery, caching, and rate-limit counters.                            | 6379      |

---

## 2. Backend — application core

The server is written in modern asynchronous Python. Every dependency is
version-pinned and reproducibly installed, so a build today is identical to a build in
a year.

| Technology | Version | Role | What it does |
|------------|---------|------|--------------|
| Python | 3.12 | Language | The programming language for the entire backend. A mature, widely-supported ecosystem with deep talent availability. |
| FastAPI | 0.115 | Web framework | Handles all API requests. Asynchronous and high-performance, with automatic, always-accurate API documentation generated from the code. |
| Uvicorn | 0.34 | Application server | The high-speed server process that runs the FastAPI application and handles concurrent connections. |
| Pydantic | 2.11 | Data validation | Validates every piece of data entering and leaving the system, preventing malformed or unsafe input from reaching business logic. |
| SQLAlchemy | 2.0 | Database layer (async) | The bridge between Python code and the database. Lets the team work with data safely in code while guarding against SQL injection. |
| asyncpg | 0.31 | Database driver | The high-performance PostgreSQL connector that lets the app talk to the database without blocking. |
| Alembic | 1.16 | Schema migrations | Version-controls the database structure. Schema changes are applied automatically and safely on every deployment. |
| httpx · aiofiles · anyio | — | Async I/O toolkit | Non-blocking HTTP requests and file handling, keeping the server responsive under load. |
| openpyxl | 3.1 | Spreadsheets | Reads and writes Excel files, powering the platform's bulk data import and export features. |
| email-validator | 2.2 | Utility | Verifies that user email addresses are well-formed during sign-up and user management. |

---

## 3. Data & background processing

Persistent storage plus a job system that moves slow work — backups, large exports —
off the user's request so the interface always stays fast.

| Technology | Version | Role | What it does |
|------------|---------|------|--------------|
| PostgreSQL | 16 | Primary database | An enterprise-grade relational database — the trusted, auditable system of record for all company and compliance data. |
| Redis | 7 | Cache & message broker | An in-memory store used as the task queue, for caching, and to enforce rate limits that protect the API from abuse. |
| Celery | 5.5 | Background jobs | Runs long tasks in the background — bulk exports and the automated nightly backup — without holding up users. |
| Celery Beat | 5.5 | Scheduler | Triggers recurring jobs on a schedule; today it runs a full database and document backup every night. |

---

## 4. Frontend — user interface

A single-page web application built with an industry-standard React toolchain. Written
in TypeScript for reliability, and typed directly against the backend's API so the two
never drift out of sync.

| Technology | Version | Role | What it does |
|------------|---------|------|--------------|
| React | 18.3 | UI framework | The foundation of the interface — the most widely adopted UI framework, ensuring longevity and easy hiring. |
| TypeScript | 5.5 | Language | Adds type-safety to the frontend, catching whole classes of bugs before code ever reaches a user. |
| Vite | 5.3 | Build tool | Compiles and bundles the application. Extremely fast for developers, and produces small, optimised production builds. |
| Tailwind CSS | 3.4 | Styling | A utility-based styling system that keeps the look consistent across the whole product and speeds up UI development. |
| TanStack Query | 5.51 | Server-state | Manages data fetching, caching, and refreshing — so screens load quickly and always show current information. |
| React Router | 6.24 | Navigation | Handles moving between the platform's pages and modules within the single-page app. |
| React Hook Form | 7.52 | Forms | Powers the many data-entry forms across the product efficiently and with minimal re-rendering. |
| Zod | 3.23 | Validation | Validates form input in the browser, giving users immediate, clear feedback before anything is submitted. |
| Framer Motion | 12 | Animation | Provides smooth, polished transitions and micro-interactions that make the interface feel refined. |
| lucide-react | 1.24 | Icons | A clean, consistent icon set used throughout the interface. |
| clsx · tailwind-merge | — | UI utilities | Helper libraries that keep component styling tidy and free of conflicts. |
| openapi-typescript | 7.0 | API contract | Generates TypeScript types directly from the backend's API specification, guaranteeing the frontend and backend agree. |

---

## 5. Security & data protection

Because Kubera holds sensitive corporate and compliance records for multiple client
companies, security is architectural rather than bolted on. Documents are protected
with layered **envelope encryption**, so no single key can unlock everything.

```
┌─────────────────────────────────────────────────────────────┐
│  ROOT MASTER KEY                                              │
│  A single top-level key, held only in secured server         │
│  configuration — never in the database.                      │
└─────────────────────────────────────────────────────────────┘
                          ↓ encrypts
┌─────────────────────────────────────────────────────────────┐
│  COMPANY KEY  (AES-256-GCM)                                   │
│  Each client company has its own key, encrypted under the     │
│  root key. This cryptographically isolates one tenant's       │
│  data from another's.                                         │
└─────────────────────────────────────────────────────────────┘
                          ↓ encrypts
┌─────────────────────────────────────────────────────────────┐
│  DOCUMENT KEY  (AES-256-GCM)                                  │
│  Every individual document is encrypted with its own unique   │
│  key, which is in turn protected by the company key.          │
└─────────────────────────────────────────────────────────────┘
```

- **cryptography (v45)** — the audited library providing AES-256-GCM, the same authenticated encryption standard used across the financial industry.
- **JWT authentication (python-jose)** — users prove their identity with signed, tamper-evident tokens rather than passwords being sent on every request.
- **Password hashing (passlib · bcrypt)** — passwords are never stored directly; only irreversible, salted hashes are kept.
- **Rate limiting (Redis-backed)** — automated abuse and brute-force attempts are throttled at the edge of the API.
- **Controlled onboarding** — companies and admins are provisioned by an operator using a protected internal key; new admins activate via a single-use, time-limited key.
- **Automatic HTTPS (Caddy)** — all traffic is encrypted in transit, with certificates provisioned and renewed automatically.
- **Automated nightly backups** — a scheduled job captures the full database and the encrypted document vault every night.

---

## 6. Infrastructure & deployment

The entire platform runs as containers, so it deploys the same way on any server with a
single command. There is no manual environment setup to get wrong.

| Technology | Version | Role | What it does |
|------------|---------|------|--------------|
| Docker & Compose | v2 | Containerisation | Packages every service into a portable container and runs the whole stack with one command — consistent from a laptop to production. |
| Caddy | 2 | Reverse proxy | The public front door. Routes traffic to the app and provisions/renews HTTPS certificates automatically at no cost. |
| Nginx | alpine | Static web server | Serves the compiled frontend efficiently to every visitor. |
| uv | 0.9 | Python packaging | A modern, extremely fast package manager that installs exact, locked dependency versions for fully reproducible builds. |

---

## 7. Quality & developer tooling

Tests and automated checks guard against regressions, and the API documents itself so
it can never fall out of date.

| Technology | Version | Role | What it does |
|------------|---------|------|--------------|
| pytest | 8.4 | Backend testing | The automated test suite for the server, run against a real database to verify behaviour before release. |
| Vitest + Testing Library | 2.0 | Frontend testing | Automated tests for the user interface, checking components behave as a real user would expect. |
| ESLint + typescript-eslint | 8.57 | Code quality | Automatically flags risky or inconsistent code before it is merged, keeping the codebase healthy. |
| Swagger UI & ReDoc | — | API documentation | Interactive, always-current API documentation generated straight from the code — useful for integrations and audits. |

---

## 8. What the technology powers

The stack above delivers a single multi-tenant platform made up of these product
modules, each with per-user access control.

| Module | Purpose |
|--------|---------|
| **DocVault** | Encrypted document storage with buckets, versioning, and access management. |
| **AuditEase** | Audit workflow and working-paper management. |
| **SecretarialEase** | Company secretarial records and statutory registers. |
| **ROC Compliance** | Registrar-of-Companies filings and compliance tracking. |
| **Assets & Sales** | Asset registers and sales/ledger records with custom fields. |
| **Admin Portal** | Company, user, notification, and activity-log management. |

---

*Confidential · Internal*
