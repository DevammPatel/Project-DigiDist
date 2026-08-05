#!/usr/bin/env bash
# End-to-end pipeline runner.
# Usage: ./run_pipeline.sh [--with-postgres-embedded]
#   By default assumes PostgreSQL is already running (edit DSN in scripts if needed).
#   --with-postgres-embedded starts the npm embedded-postgres binaries on port 5433.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--with-postgres-embedded" ]]; then
    PGDIR=node_modules/@embedded-postgres/darwin-arm64/native   # adjust for your platform
    export LD_LIBRARY_PATH="$PWD/$PGDIR/lib"
    [[ -d /tmp/pgdata ]] || "$PGDIR/bin/initdb" -D /tmp/pgdata -U postgres --auth=trust -E UTF8
    "$PGDIR/bin/pg_ctl" -D /tmp/pgdata -o "-p 5433 -k /tmp" -l /tmp/pglog start || true
    sleep 2
fi

echo "== 1/3 Generating raw source data =="
python3 scripts/generate_raw_data.py

echo "== 2/3 Running ETL into PostgreSQL =="
python3 scripts/etl_pipeline.py

echo "== 3/3 Computing DPI and exporting for Power BI =="
python3 - << 'EOF'
import psycopg2
c = psycopg2.connect(host='/tmp', port=5433, user='postgres', dbname='digital_economy')
c.cursor().execute(open('sql/compute_dpi.sql').read()); c.commit(); c.close()
print("DPI materialized view refreshed")
EOF
python3 scripts/export_powerbi.py

echo "Done. Open exports/ in Power BI (see docs/POWERBI_SETUP.md)."
