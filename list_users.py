#!/usr/bin/env python3
"""List company users directly from the database (operator tool).

Runs psql inside the postgres container via `docker compose`, reading the DB
name/user from the .env next to this script. Lists users across ALL companies.

Usage:
    python3 list_users.py                 # all users
    python3 list_users.py acme            # filter by email OR company name substring

Must be run from the project folder on the host where the containers run.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
SEP = "\x1f"  # unit separator — won't collide with real data


def load_env(path):
    if not os.path.exists(path):
        sys.exit(f"error: no .env file found at {path}")
    env = {}
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def compose_cmd():
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            r = subprocess.run(cmd + ["version"], capture_output=True, text=True, cwd=HERE, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    sys.exit("error: could not find `docker compose` (is Docker installed and are you in the project folder?)")


def run_psql(sql, env):
    cmd = compose_cmd() + [
        "exec", "-T", "postgres",
        "psql", "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"],
        "-tA", "-F", SEP, "-c", sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        sys.exit(f"error: psql failed:\n{r.stderr.strip()}")
    rows = [ln.split(SEP) for ln in r.stdout.splitlines() if ln.strip() != ""]
    return rows


def esc(s):
    return s.replace("'", "''")


def main():
    env = load_env(ENV_PATH)
    for k in ("POSTGRES_USER", "POSTGRES_DB"):
        if not env.get(k):
            sys.exit(f"error: {k} is not set in .env")

    where = ""
    if len(sys.argv) > 1:
        f = esc(sys.argv[1].lower())
        where = f"WHERE lower(u.email) LIKE '%{f}%' OR lower(c.name) LIKE '%{f}%'"

    sql = f"""
        SELECT c.name, u.email, u.full_name, u.role, u.is_active::text,
               (u.deleted_at IS NOT NULL)::text, u.id
        FROM company_users u JOIN companies c ON c.id = u.company_id
        {where}
        ORDER BY c.name, u.role, u.email;
    """
    rows = run_psql(sql, env)
    if not rows:
        print("No users found.")
        return

    print(f"\n{len(rows)} user(s):\n")
    current = None
    for name, email, full_name, role, is_active, deleted, uid in rows:
        if name != current:
            current = name
            print(f"  ── {name} ──")
        if deleted in ("t", "true"):
            status = "DELETED"
        elif is_active in ("t", "true"):
            status = "active"
        else:
            status = "INACTIVE"
        print(f"     {email}")
        print(f"       name={full_name!r}  role={role}  status={status}")
        print(f"       id={uid}")
    print()


if __name__ == "__main__":
    main()
