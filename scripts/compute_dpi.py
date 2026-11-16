"""Build the District Prosperity Index views by running sql/compute_dpi.sql."""
from pathlib import Path

from db import get_conn

ROOT = Path(__file__).resolve().parents[1]

conn = get_conn()
conn.cursor().execute((ROOT / "sql" / "compute_dpi.sql").read_text())
conn.commit()
conn.close()
print("DPI materialized view refreshed")
