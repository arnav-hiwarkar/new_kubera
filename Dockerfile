FROM python:3.12-slim

# uv provides fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/

WORKDIR /code

# System deps: postgresql-client provides psql + pg_dump (used by the nightly
# backup task and the operator scripts). WeasyPrint requires runtime shared libraries
# (pango, harfbuzz, gdk-pixbuf, libffi, shared-mime-info) and fonts supporting Unicode
# and Indian currency symbols (fonts-dejavu-core, fonts-noto-core for U+20B9 ₹).
# No compiler is needed — every pinned dependency ships a cp312 manylinux wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 \
    libffi8 shared-mime-info fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# Run the application as a non-root user. api/worker/beat hold the root KEK and
# the decrypted vault in memory, so a remote-code-execution bug in FastAPI should
# not also hand over uid 0 inside the container.
#
# The data directories are created AND chowned here, before any volume is
# attached, because Docker copies the image path's ownership into a *new* named
# volume. Fresh deployments therefore get kubera-owned volumes automatically;
# only pre-existing root-owned volumes need the one-time chown documented in
# docs/SECURITY_HARDENING.md.
RUN groupadd --system --gid 10001 kubera \
    && useradd --system --uid 10001 --gid kubera --no-create-home --shell /usr/sbin/nologin kubera \
    && mkdir -p /data/vault /data/backups /var/lib/kubera-beat \
    && chown -R kubera:kubera /data /var/lib/kubera-beat

# Keep the project virtualenv OUTSIDE /code so the docker-compose bind-mount of
# `.:/code` (used for --reload) can't shadow it. Put it on PATH so uvicorn /
# celery / alembic resolve directly, and expose the app package via PYTHONPATH.
#
# PYTHONDONTWRITEBYTECODE: as a non-root user Python cannot write .pyc files next
# to the sources in /code and would retry on every import. The venv is already
# byte-compiled by UV_COMPILE_BYTECODE.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/code \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies first (cached until the lockfile changes). --frozen fails
# if pyproject.toml and uv.lock are out of sync, guaranteeing reproducibility.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# App source (commands are supplied by docker-compose).
# NOTE: .dockerignore decides what lands here. It must exclude every secret and
# all tenant data — see unit_tests/test_dockerignore_covers_secrets.py.
COPY --chown=kubera:kubera . .

USER kubera

EXPOSE 8000
