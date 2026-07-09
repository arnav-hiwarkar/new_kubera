FROM python:3.12-slim

WORKDIR /code

# Install system deps for asyncpg and pg_dump (for backup job)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/code

EXPOSE 8000
