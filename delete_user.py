#!/usr/bin/env python3
"""Hard-delete a company user directly from the database (operator tool).

IRREVERSIBLE. Runs psql inside the postgres container via `docker compose`,
reading the DB name/user from the .env next to this script. Looks the user up by
email, shows who it is, guards against removing a company's last active admin,
requires confirmation, detaches any direct reports, then deletes the row.

Usage:
    python3 delete_user.py                 # prompts for the email
    python3 delete_user.py user@corp.com   # target passed as an argument

Must be run from the project folder on the host where the containers run.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
SEP = "\x1f"


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


COMPOSE = None


def run_psql(sql, env, expect_rows=True):
    global COMPOSE
    if COMPOSE is None:
        COMPOSE = compose_cmd()
    cmd = COMPOSE + [
        "exec", "-T", "postgres",
        "psql", "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"],
        "-tA", "-F", SEP, "-c", sql,
    ]
    # stdin=DEVNULL: `docker compose exec` would otherwise drain our stdin and
    # starve the later confirmation prompt.
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        return None, r.stderr.strip()
    if expect_rows:
        rows = [ln.split(SEP) for ln in r.stdout.splitlines() if ln.strip() != ""]
        return rows, None
    return r.stdout.strip(), None


def esc(s):
    return s.replace("'", "''")


def prompt(label):
    try:
        return input(label).strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\naborted")


def main():
    env = load_env(ENV_PATH)
    for k in ("POSTGRES_USER", "POSTGRES_DB"):
        if not env.get(k):
            sys.exit(f"error: {k} is not set in .env")

    email = sys.argv[1].strip() if len(sys.argv) > 1 else prompt("Email of the user to delete: ")
    if not email:
        sys.exit("error: email cannot be empty")

    rows, err = run_psql(f"""
        SELECT u.id, u.full_name, u.role, u.is_active::text, c.name, u.company_id
        FROM company_users u JOIN companies c ON c.id = u.company_id
        WHERE lower(u.email) = lower('{esc(email)}');
    """, env)
    if err:
        sys.exit(f"error: lookup failed:\n{err}")
    if not rows:
        sys.exit(f"error: no user with email {email!r}")

    uid, full_name, role, is_active, company_name, company_id = rows[0]

    print("\nMatched user:")
    print(f"  email   : {email}")
    print(f"  name    : {full_name}")
    print(f"  role    : {role}")
    active = is_active in ("t", "true")
    print(f"  active  : {'yes' if active else 'no'}")
    print(f"  company : {company_name}")
    print(f"  id      : {uid}")

    # Guard: don't strand a company without an active admin.
    if role == "admin" and active:
        cnt, err = run_psql(
            f"SELECT count(*) FROM company_users "
            f"WHERE company_id = '{company_id}' AND role = 'admin' AND is_active = true;",
            env,
        )
        if not err and cnt and int(cnt[0][0]) <= 1:
            print(f"\n⚠  This is the ONLY active admin of '{company_name}'.")
            print("   Deleting it leaves the company with no one who can manage it.")
            if prompt("   Type 'DELETE LAST ADMIN' to proceed anyway: ") != "DELETE LAST ADMIN":
                sys.exit("aborted")

    print(f"\n⚠  This PERMANENTLY deletes the user above. This cannot be undone.")
    if prompt("Retype the email exactly to confirm: ") != email:
        sys.exit("error: email did not match — aborted")

    # Detach any direct reports first (self-referential FK has no cascade).
    _, err = run_psql(
        f"UPDATE company_users SET manager_id = NULL WHERE manager_id = '{uid}';",
        env, expect_rows=False,
    )
    if err:
        sys.exit(f"error: could not detach reports:\n{err}")

    out, err = run_psql(
        f"DELETE FROM company_users WHERE id = '{uid}';",
        env, expect_rows=False,
    )
    if err:
        print(f"\nerror: delete failed:\n{err}")
        print("\n(The user likely still owns tenant data with a restricting foreign "
              "key — e.g. documents or records. Reassign or remove those first.)")
        sys.exit(1)

    print(f"\n✓ Deleted {email} ({out or 'ok'}).")


if __name__ == "__main__":
    main()
