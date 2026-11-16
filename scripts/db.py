"""Shared PostgreSQL connection settings for every pipeline script.

The connection string comes from the DATABASE_URL environment variable, for
example `postgresql://postgres:postgres@localhost:5432/digital_economy`.
When it is not set, the scripts use the local embedded Postgres that
`run_pipeline.sh --with-postgres-embedded` starts (unix socket in /tmp, port 5433).
"""
import os

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import make_dsn, parse_dsn

DEFAULT_DSN = "host=/tmp port=5433 user=postgres dbname=digital_economy"


def dsn() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_DSN


def get_conn():
    return psycopg2.connect(dsn())


def ensure_database():
    """Create the target database if the server does not have it yet."""
    params = parse_dsn(dsn())
    target = params.get("dbname", "postgres")
    admin = psycopg2.connect(make_dsn(dsn(), dbname="postgres"))
    admin.autocommit = True  # CREATE DATABASE cannot run inside a transaction
    cur = admin.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
    if not cur.fetchone():
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        print(f"Created database {target}")
    admin.close()


if __name__ == "__main__":
    ensure_database()
