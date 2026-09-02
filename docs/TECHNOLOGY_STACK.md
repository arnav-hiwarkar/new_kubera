# Kubera Platform — Complete Technical Stack Reference

> Comprehensive documentation of all frameworks, libraries, runtime environments, storage engines, security architectures, and deployment infrastructure powering the Kubera multi-tenant enterprise audit and compliance platform.

---

## Table of Contents
1. [Architecture & Traffic Flow Overview](#1-architecture--traffic-flow-overview)
2. [Frontend Technology Stack](#2-frontend-technology-stack)
3. [Backend Technology Stack](#3-backend-technology-stack)
4. [Database, Caching & Persistent Storage](#4-database-caching--persistent-storage)
5. [Security, Cryptography & Authentication](#5-security-cryptography--authentication)
6. [Zero-Downtime Maintenance Gateway & Edge Proxy](#6-zero-downtime-maintenance-gateway--edge-proxy)
7. [Deployment, Containers & Infrastructure](#7-deployment-containers--infrastructure)
8. [Testing, Quality & Developer Tooling](#8-testing-quality--developer-tooling)
9. [Product Modules & Capability Mapping](#9-product-modules--capability-mapping)

---

## 1. Architecture & Traffic Flow Overview

Kubera is designed as a set of isolated, containerized micro-services orchestrated with Docker Compose. Public inbound traffic traverses a resilient, dual-layer proxy topology featuring automatic TLS termination, instantaneous zero-downtime maintenance switching, and isolated internal communication.

```
                                      ┌─────────────────────────────────────────────────────────┐
                                      │                      PUBLIC INTERNET                    │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │ Port 80 / 443
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │                      Caddy 2 Proxy                      │
                                      │        • Automatic TLS (Let's Encrypt / ZeroSSL)        │
                                      │        • Reverse proxy to internal Gateway              │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │ Internal HTTP
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │                   Nginx Gateway Proxy                   │
                                      │       • Instantaneous App/Maintenance mode switch       │
                                      │       • Dynamic upstream resolution (valid=5s)          │
                                      └─────────────┬─────────────────────────────┬─────────────┘
                                                    │                             │
                                  [App Mode]        │                             │  [Maintenance Mode]
                                                    ▼                             ▼
                    ┌───────────────────────────────────────────────┐   ┌───────────────────────────────┐
                    │               Frontend (Nginx)                │   │  Standalone Maintenance App   │
                    │   • React 18 SPA + Static Asset Caching       │   │  • Zero-dependency HTML5/JS   │
                    │   • Internal `/api/*` reverse proxy to API    │   │  • Live sync countdown timer  │
                    └───────────────────────┬───────────────────────┘   └───────────────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │               API Server (FastAPI)            │
                    │      • Python 3.12 ASGI Application           │
                    │      • Business Logic, Auth, Crypto & ORM     │
                    └───────┬───────────────────────────────┬───────┘
                            │                               │
            ┌───────────────┴───────────────┐       ┌───────┴───────────────────────┐
            ▼                               ▼       ▼                               ▼
┌───────────────────────┐       ┌───────────────────────┐       ┌───────────────────────┐
│     PostgreSQL 16     │       │        Redis 7        │       │   Celery Worker/Beat  │
│  • System of Record   │       │  • Rate Limiting      │       │  • Background tasks   │
│  • Relational DB      │       │  • Celery Message Q   │       │  • Nightly Backups    │
│  • AsyncPG Driver     │       │  • Cache Layer        │       │  • Heavy PDF/Exports  │
└───────────────────────┘       └───────────────────────┘       └───────────────────────┘
```

---

## 2. Frontend Technology Stack

The client is a responsive, single-page web application (SPA) built with a modern React + TypeScript toolchain.

| Category | Technology | Version | Description & Role |
|---|---|---|---|
| **Core UI Framework** | **React** | `18.3.1` | Component-based UI engine utilizing modern Concurrent features and Hooks. |
| **Language** | **TypeScript** | `5.5.3` | Type safety, typed API contracts, and compile-time correctness across the entire UI codebase. |
| **DOM Renderer** | **React-DOM** | `18.3.1` | Browser-specific rendering engine for React tree mounting. |
| **Bundler & Dev Server** | **Vite** | `5.3.3` | Fast ESM-native development server and Rollup-based production bundler with `@vitejs/plugin-react` (`v4.3.1`). |
| **Client Routing** | **React Router DOM** | `6.24.0` | Declarative routing with route guards (`ModuleGuard`, `RoleGuard`), nested layouts, and URL parameters. |
| **Server State & Caching** | **TanStack React Query** | `5.51.0` | Asynchronous data fetching, background stale-while-revalidate caching, optimistic updates, and garbage collection. |
| **Form Handling** | **React Hook Form** | `7.52.0` | High-performance uncontrolled form state management and input bindings with minimal re-renders. |
| **Client Validation** | **Zod** | `3.23.8` | Declarative schema validation for user inputs, dynamic forms, and API responses. |
| **CSS Framework** | **Tailwind CSS** | `3.4.4` | Utility-first CSS framework integrated with **PostCSS** (`8.4.39`) and **Autoprefixer** (`10.4.19`). |
| **Class Utilities** | **clsx** & **tailwind-merge** | `2.1.1` / `2.4.0` | Dynamic CSS class concatenation and intelligent Tailwind class conflict resolution. |
| **Iconography** | **Lucide React** | `1.24.0` | Comprehensive, consistent SVG icon set across all platform screens and modals. |
| **Animations** | **Framer Motion** | `12.42.2` | Production-grade motion library for layout transitions, drawers, dropdowns, and micro-interactions. |
| **3D & Graph Visualization** | **3D Force Graph** & **Three.js** | `1.80.0` / `0.185.1` | Interactive 3D WebGL knowledge graph powering the DocVault cross-document entity and reference visualizer. |
| **API Contract Generator** | **openapi-typescript** | `7.0.0` | Automated CLI tool generating TypeScript interfaces directly from FastAPI's live `/openapi.json` endpoint. |
| **Production Web Server** | **Nginx** | `alpine` | Serves compiled static assets with immutable cache headers for hashed bundles, dynamic `no-cache` for `index.html`, and internal API reverse proxy. |

---

## 3. Backend Technology Stack

The backend application is an asynchronous, high-throughput REST API and background worker system written in Python 3.12.

| Category | Technology | Version | Description & Role |
|---|---|---|---|
| **Runtime & Language** | **Python** | `3.12` | Modern asynchronous Python runtime running inside `python:3.12-slim` base images. |
| **Dependency Manager** | **Astral uv** | `0.9.28` | Deterministic, high-speed Python package manager resolving from `pyproject.toml` and locked via `uv.lock`. |
| **Web Framework** | **FastAPI** | `0.115.12` | Asynchronous ASGI web framework featuring automatic OpenAPI/Swagger documentation, dependency injection, and high throughput. |
| **ASGI Server** | **Uvicorn** | `0.34.3` | Production ASGI web server running with standard async loop optimizations (`uvloop`, `httptools`). |
| **Data Validation & Settings** | **Pydantic** & **pydantic-settings** | `2.11.5` / `2.9.1` | Strict runtime typing, schema serialization, request/response models, and environment variable configuration from `.env`. |
| **Asynchronous I/O Engine** | **AnyIO** & **asyncio** | `4.9.0` | Low-level structured async concurrency foundation. |
| **Async HTTP Client** | **HTTPX** | `0.28.1` | Asynchronous HTTP client for outbound requests, webhooks, and service integration tests. |
| **File I/O Toolkit** | **aiofiles** & **python-multipart** | `23.2.1` / `0.0.20` | Non-blocking asynchronous file system reads/writes and streaming multipart upload handlers. |
| **PDF Rendering Engine** | **WeasyPrint** & **Jinja2** | `>=62.0` / `>=3.1.0` | Headless HTML/CSS to PDF rendering engine using Jinja2 templates for compliance audit packs and statutory registers. |
| **Spreadsheet Engine** | **OpenPyXL** | `>=3.1.0` | Native Excel (`.xlsx`) parser and builder supporting flexible column mapping, Trial Balance import, and asset register exports. |
| **OS Graphics / Font Libs** | **Pango, HarfBuzz, GDK-Pixbuf** | Linux system deps | OS-level rendering libraries for WeasyPrint with Unicode and Indian Rupee (`₹`) font support (`fonts-dejavu-core`, `fonts-noto-core`). |
| **Background Task Queue** | **Celery** | `5.5.3` | Distributed background worker executing asynchronous jobs (data imports, report generation, vault backup tasks). |
| **Task Scheduler** | **Celery Beat** | `5.5.3` | Cron-based scheduler triggering automated recurring tasks (nightly database and vault backups). |

---

## 4. Database, Caching & Persistent Storage

| Component | Technology | Version | Role & Configuration |
|---|---|---|---|
| **Primary Relational DB** | **PostgreSQL** | `16-alpine` | Auditable system of record storing multi-tenant business data, audit trails, and metadata. |
| **Async Database Driver** | **asyncpg** | `0.31.0` | Ultra-fast native PostgreSQL async connector communicating over TCP. |
| **Object-Relational Mapping** | **SQLAlchemy** | `2.0.41` | Modern async ORM using `async_sessionmaker`, declarative models, and strict tenant isolation filters. |
| **Database Migrations** | **Alembic** | `1.16.2` | Declarative, version-controlled schema migrations executed automatically at container startup (`alembic upgrade head`). |
| **In-Memory Cache & Broker** | **Redis** | `7-alpine` | Multi-purpose in-memory datastore acting as Celery broker, Celery results backend, and rate-limiting counter store. |
| **Encrypted Document Storage** | **Filesystem Volume** | Docker Named Volume | Local storage backed by the `vault_data` volume (`/data/vault`), storing per-file AES-256-GCM encrypted payloads. |
| **Disaster Recovery Backups** | **PostgreSQL Client & Tar** | `postgresql-client` | Nightly automated `pg_dump -Fc` (custom-format, `pg_restore`-only) dumps and compressed vault tarballs (`.tar.gz`) stored in the `backup_data` volume (`/data/backups`). |

---

## 5. Security, Cryptography & Authentication

Kubera enforces multi-tenant cryptographic isolation and defense-in-depth access controls:

### Multi-Layer Envelope Encryption (KMS Pattern)
Implemented via the Python **`cryptography` (`v45.0.4`)** library using **AES-256-GCM** authenticated encryption with random 12-byte nonces:

```
[ Root Master KEK ] (32-byte master key in server environment)
         │
         ▼ (Encrypts)
[ Company KEK ] (Per-tenant AES-256 key; cryptographically isolates tenant data)
         │
         ▼ (Encrypts)
[ Document DEK ] (Unique Data Encryption Key generated per individual file)
         │
         ▼ (Encrypts)
[ File Ciphertext ] (Encrypted file payload stored on disk in /data/vault)
```

### Identity, Tokens & Authorization
* **Password Hashing:** `passlib[bcrypt]` / `bcrypt` with cryptographic salts.
* **Token Authentication:** `python-jose[cryptography]` (`3.4.0`) issuing cryptographically signed JWT access tokens (30m lifetime) and refresh tokens (7d lifetime).
* **Role-Based Access Control (RBAC):** Strict hierarchy enforcing privileges across `Admin`, `Manager`, `Employee`, and external `Auditor` roles.
* **Module-Level Feature Gates:** Backend dependency factories (`require_module`, `require_role`) ensuring access is enforced server-side before request execution.
* **Distributed Rate Limiting:** Fixed-window rate limiter (`app/rate_limit.py`) backed by Redis to defend unauthenticated login and activation endpoints against brute-force attacks (with automatic fail-open resilience).
* **Operator Security:** Master `X-Internal-API-Key` required for tenant creation, account resets, and company de-provisioning.

---

## 6. Zero-Downtime Maintenance Gateway & Edge Proxy

Kubera includes an edge architecture designed for zero-downtime maintenance windows and live migrations:

```
                    ┌─────────────────────────┐
                    │     Caddy 2 Edge Proxy   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    Gateway (Nginx)      │
                    │  keepalive_timeout: 0   │
                    │  resolver valid: 5s     │
                    └────┬───────────────┬────┘
                         │               │
      [Normal Mode]      │               │      [Maintenance Mode]
                         ▼               ▼
                 ┌───────────────┐ ┌───────────────┐
                 │ Frontend/API  │ │  Maintenance  │
                 │ Container     │ │  Page (503)   │
                 └───────────────┘ └───────────────┘
```

* **Edge Reverse Proxy:** **Caddy 2 (`caddy:2-alpine`)** automatically handles public port 80/443 traffic and provisions/renews Let's Encrypt / ZeroSSL TLS certificates.
* **Maintenance Gateway:** **Nginx (`gateway/Dockerfile`)** acts as a persistent traffic switch between live application containers and a standalone maintenance page.
* **Zero Upstream Linger:** Configured with `keepalive_timeout 0` and dynamic DNS resolution so mode switches take effect on the very next HTTP request.
* **Synchronized Countdown:** Standalone HTML5 / CSS3 / Vanilla JS maintenance UI synchronized with a persistent Docker volume (`maintenance_runtime`) and real-time auto-refresh upon system recovery.
* **Operator CLI:** `maintenance.py` (`on`, `off`, `status`) CLI verifying backend health probes (`/readyz`) before bringing traffic back online.

---

## 7. Deployment, Containers & Infrastructure

The entire platform deploys reproducibly onto any Linux/macOS host with Docker and Docker Compose v2.

### Orchestrated Container Services (`docker-compose.yml`)

| Service Name | Base Docker Image | Exposed / Internal Port | Purpose |
|---|---|---|---|
| **`caddy`** | `caddy:2-alpine` | `80:80`, `443:443` | Public edge reverse proxy & automated SSL/TLS termination. |
| **`gateway`** | `nginx:alpine` (custom) | Internal (`gateway:80`) | Dynamic App / Maintenance mode routing switch. |
| **`frontend`** | `nginx:alpine` (multi-stage) | Internal (`frontend:80`) | Production Nginx server hosting built Vite SPA bundle. |
| **`api`** | `python:3.12-slim` | `127.0.0.1:8000:8000` | FastAPI ASGI server; runs Alembic migrations on boot. |
| **`worker`** | `python:3.12-slim` | Internal | Celery asynchronous worker process. |
| **`beat`** | `python:3.12-slim` | Internal | Celery Beat periodic task scheduler. |
| **`postgres`** | `postgres:16-alpine` | Internal (`postgres:5432`, `data` network) | Relational database. Publishes no host port in production. |
| **`redis`** | `redis:7-alpine` | Internal (`redis:6379`, `data` network) | In-memory broker, cache, and rate-limiting store. Requires `--requirepass`; publishes no host port in production. |


### Network exposure

`caddy` is the only service published to a wildcard address. Two Docker networks
separate the tiers: `edge` (`caddy`, `gateway`, `frontend`, `api`) and `data`
(`api`, `worker`, `beat`, `postgres`, `redis`). `api` is the only member of both,
so the edge containers have no route to the database or broker.

Local development ports (Postgres on `127.0.0.1:5433`, Redis on `127.0.0.1:6379`,
`uvicorn --reload`) come from `docker-compose.override.yml`, which is gitignored
and must never exist on a server. See `docs/SECURITY_HARDENING.md`.

### Docker Named Volumes
* `pgdata`: Persistent PostgreSQL database data directory.
* `vault_data`: Encrypted document vault storage (`/data/vault`).
* `backup_data`: Automated `pg_dump -Fc` database dumps and vault archives (`/data/backups`).
* `caddy_data` & `caddy_config`: Persistent TLS certificates and edge configurations.
* `maintenance_runtime`: Shared runtime volume storing active gateway routing configs and maintenance timestamps.
* `beat_data`: Celery Beat schedule database (`/var/lib/kubera-beat`), so a redeploy does not re-fire missed schedules.

---

## 8. Testing, Quality & Developer Tooling

* **Backend Testing:**
  * **Pytest (`8.4.1`)**: Automated test runner executing against an isolated PostgreSQL test database (`kubera_test`).
  * **Pytest-AsyncIO (`1.0.0`)**: Asynchronous test fixtures and session lifecycle management.
* **Frontend Testing:**
  * **Vitest (`2.0.0`)**: Fast, Vite-native unit and component test runner.
  * **JSDOM (`24.1.0`)**: Simulated browser DOM environment for headless testing.
  * **React Testing Library (`16.0.0`)** with `@testing-library/jest-dom` and `@testing-library/user-event`.
* **Static Analysis & Linting:**
  * **ESLint (`8.57.0`)** with `@typescript-eslint/parser` and React Hooks rules.
* **Interactive API Documentation:**
  * **Swagger UI** (interactive testing at `/docs`).
  * **ReDoc** (structured technical specification at `/redoc`).

---

## 9. Product Modules & Capability Mapping

| Module | Core Functionality | Primary Tech Used |
|---|---|---|
| **DocVault** | Multi-tenant encrypted file storage, document tagging, versioning, and interactive 3D relationship graphing. | AES-256-GCM Envelope Encryption, `aiofiles`, Three.js, `3d-force-graph` |
| **AuditEase** | Statutory audit working papers, trial balance import, sign convention rules, audit query tracking, and auditor portal. | `openpyxl`, `SQLAlchemy`, TanStack React Query, Multi-Auditor Grants |
| **Fixed Asset Register** | Asset master records, asset costing, acquisitions/disposals, custom fields, and Companies Act / IT Act depreciation engines. | Custom Calculation Trace Engine, `openpyxl`, `WeasyPrint` |
| **SecretarialEase** | Corporate secretarial records, board meeting minutes, director registers, and statutory registers. | `SQLAlchemy`, `WeasyPrint`, Jinja2 templates |
| **ROC Compliance** | Registrar of Companies filing calendar, statutory event tracking, and compliance document sync. | Background Celery Beat scheduler, `WeasyPrint`, PostgreSQL |
| **Sales Tracking** | Team sales entries, flexible custom fields, and employee hierarchy tracking. | JSONB dynamic fields, `openpyxl` bulk export/import |
| **KRA & Appraisal** | Employee goal-setting cycles, target vs. achieved progress tracking, manager approval workflows, and appraisal exports. | Hierarchical user scoping, `openpyxl`, React Hook Form |
| **Admin Portal** | Company onboarding, user directory, module access control, password management, and audit activity logging. | JWT Auth, Redis rate-limiting, Operator CLI tools |
