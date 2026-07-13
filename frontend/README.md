# Kubera Frontend

React + TypeScript + Vite frontend for the Kubera V1 backend (FastAPI, `http://localhost:8000`).

## Stack

- **React 18** + **TypeScript** + **Vite**
- **Tailwind CSS** — design tokens ported from `frontend_reference_old/css/base.css`
- **React Router v6** — two structurally-separated identity trees
- **TanStack Query v5** — server state
- **openapi-typescript** — types generated from the live OpenAPI schema

## Getting started

```bash
npm install
npm run gen:api      # regenerate src/api/schema.d.ts from http://localhost:8000/openapi.json
npm run dev          # dev server on :5173, proxies /api -> :8000
npm run build        # tsc + vite build (must be clean)
npm run test         # vitest (auth-guard rendering tests)
```

## Two identities, two isolated route trees

The backend has exactly **two identity systems** (`company_user`, `auditor`), distinguished
by a `principal_type` JWT claim; each backend dependency rejects the other's token. The
frontend mirrors this at every layer:

| Layer | Company | Auditor |
|-------|---------|---------|
| Routes | `/login`, `/app/*` | `/auditor/login`, `/auditor/register`, `/auditor/app/*` |
| Guard | `CompanyGuard` | `AuditorGuard` |
| Auth store | `useCompanyAuth` | `useAuditorAuth` |
| Token storage key | `kubera.company.tokens` | `kubera.auditor.tokens` |
| HTTP client | `companyClient` | `auditorClient` |
| Refresh endpoint | `/auth/company/refresh` | `/auth/auditor/refresh` |

Each guard only ever consults its own auth context, which only reads its own token
namespace. A token belonging to the other identity is invisible — verified by the
rendering tests in `src/auth/authGuards.test.tsx`.

## Layout

```
src/
  api/          # typed client layer — every network call goes through here
    schema.d.ts   generated types (npm run gen:api)
    http.ts       fetch wrapper + refresh/retry
    clients/      company.ts, auditor.ts (identity-scoped instances)
    endpoints/    one module per backend router
    enums.ts      backend enum values + StatusBadge tone map
    types.ts      convenience aliases over schema.d.ts
  auth/         # createIdentityAuth factory + company/ + auditor/ instances
  components/ui/ # shared component library (DataTable, Modal, StatusBadge, …)
  config/       # navigation.ts — sidebar built from real backend modules
  layouts/      # CompanyShell, AuditorShell
  pages/        # company/, auditor/, ModulePlaceholder
  routes/       # company.routes, auditor.routes, index (top-level router)
```

**Rule:** components never call `fetch`/`axios` directly — always go through `src/api`.
