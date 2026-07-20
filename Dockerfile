FROM python:3.12-slim

# uv provides fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/

WORKDIR /code

# System deps: postgresql-client provides psql + pg_dump (used by the nightly
# backup task and the operator scripts). No compiler is needed — every pinned
# dependency ships a cp312 manylinux wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Keep the project virtualenv OUTSIDE /code so the docker-compose bind-mount of
# `.:/code` (used for --reload) can't shadow it. Put it on PATH so uvicorn /
# celery / alembic resolve directly, and expose the app package via PYTHONPATH.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/code

# Install dependencies first (cached until the lockfile changes). --frozen fails
# if pyproject.toml and uv.lock are out of sync, guaranteeing reproducibility.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source (commands are supplied by docker-compose).
COPY . .

EXPOSE 8000
