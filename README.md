# Kubera V1 Backend

Multi-tenant backend for docVault, AuditEase, SecretarialEase, and ROC Compliance.

## Tech Stack

- **Framework:** FastAPI (async)
- **Database:** PostgreSQL 16 + SQLAlchemy 2.0 (asyncpg)
- **Migrations:** Alembic
- **Background Jobs:** Celery + Redis
- **Auth:** JWT (access + refresh tokens, separate company/auditor identity systems)
- **Encryption:** AES-256-GCM, two-layer envelope encryption (root KEK → company KEK → document DEK)

## Quick Start (Fresh Machine)

### Prerequisites

- Docker & Docker Compose v2+
- Git

### Setup

1. **Clone the repo:**
   ```bash
   git clone <repo-url> kubera && cd kubera
   ```

2. **Create your `.env` file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set real values for:
   - `JWT_SECRET_KEY` — random 64-char string
   - `ROOT_MASTER_KEK` — 64 hex chars (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `INTERNAL_API_KEY` — any secret string for company creation endpoint

3. **Start the stack:**
   ```bash
   docker compose up -d --build
   ```

4. **Run migrations:**
   ```bash
   docker compose exec api alembic upgrade head
   ```

5. **Open Swagger UI:**
   ```
   http://localhost:8000/docs
   ```

### Running Tests

```bash
docker compose exec api pytest -v
```

### Services

| Service  | Port  | Description              |
|----------|-------|--------------------------|
| api      | 8000  | FastAPI application      |
| worker   | —     | Celery worker            |
| beat     | —     | Celery beat scheduler    |
| postgres | 5432  | PostgreSQL 16            |
| redis    | 6379  | Redis 7 (broker/backend) |

## API Docs

Once the stack is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
