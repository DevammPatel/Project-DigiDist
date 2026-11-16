#!/usr/bin/env bash
# End-to-end pipeline runner.
# Usage: ./run_pipeline.sh [--with-postgres-embedded]
#   By default connects to the PostgreSQL server named in DATABASE_URL, e.g.
#     DATABASE_URL=postgresql://postgres:postgres@localhost:5432/digital_economy
#   --with-postgres-embedded starts the npm embedded-postgres binaries on port 5433
#   and uses them instead (no DATABASE_URL needed).
set -euo pipefail
cd "$(dirname "$0")"

# Use the project's virtual environment when one exists and none is active.
PY=python3
if [[ -z "${VIRTUAL_ENV:-}" && -x .venv/bin/python ]]; then PY=.venv/bin/python; fi

if [[ "${1:-}" == "--with-postgres-embedded" ]]; then
    PGDIR=$(ls -d node_modules/@embedded-postgres/*/native 2>/dev/null | head -1 || true)
    if [[ -z "$PGDIR" ]]; then
        echo "Embedded Postgres not found. Run: npm install @embedded-postgres/<your-platform>" >&2
        exit 1
    fi
    export LD_LIBRARY_PATH="$PWD/$PGDIR/lib"
    unset DATABASE_URL   # scripts fall back to the embedded server (see scripts/db.py)
    [[ -d /tmp/pgdata ]] || "$PGDIR/bin/initdb" -D /tmp/pgdata -U postgres --auth=trust -E UTF8
    "$PGDIR/bin/pg_ctl" -D /tmp/pgdata -o "-p 5433 -k /tmp" -l /tmp/pglog start || true
    sleep 2
fi

echo "== 1/4 Generating raw source data =="
"$PY" scripts/generate_raw_data.py

echo "== 2/4 Running ETL into PostgreSQL =="
"$PY" scripts/etl_pipeline.py

echo "== 3/4 Computing DPI and exporting for Power BI =="
"$PY" scripts/compute_dpi.py
"$PY" scripts/export_powerbi.py

echo "== 4/4 Exporting data for the website =="
"$PY" scripts/export_site.py

echo "Done. Preview the site with: python3 -m http.server 8000 --directory site"
