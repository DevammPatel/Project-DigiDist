"""Export one compact JSON file that the static website in site/ reads.

Output: site/data/dashboard.json. The website has no server and no database;
everything it shows comes from this file, so it is rebuilt on every pipeline run.
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from db import get_conn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# Must match the weights in sql/compute_dpi.sql.
INDICATORS = [
    {"key": "upi", "label": "UPI value per person", "unit": "INR per year", "weight": 0.30},
    {"key": "bb", "label": "Broadband subscribers", "unit": "per 100 people", "weight": 0.25},
    {"key": "gst", "label": "GST registrations", "unit": "per 1,000 people", "weight": 0.20},
    {"key": "egov", "label": "e-Gov transactions", "unit": "per person", "weight": 0.15},
    {"key": "lit", "label": "Literacy rate", "unit": "%", "weight": 0.10},
]


def clean(value):
    """Turn a database value into something JSON can hold (NaN becomes null)."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 2)
    if hasattr(value, "item"):  # numpy scalar
        return clean(value.item())
    return value


conn = get_conn()


def query(sql):
    return pd.read_sql(sql, conn)


dpi = query("SELECT * FROM warehouse.mv_dpi ORDER BY district_id, year")
years = sorted(int(y) for y in dpi.year.unique())

# One record per district, with one value per year in the same order as `years`.
districts = []
for district_id, rows in dpi.groupby("district_id", sort=True):
    by_year = {int(r.year): r for r in rows.itertuples()}
    first = rows.iloc[0]

    def series(column):
        return [clean(getattr(by_year[y], column)) if y in by_year else None for y in years]

    districts.append({
        "id": int(district_id),
        "name": first.district_name,
        "state": first.state_name,
        "pop": clean(first.population),
        "lit": clean(first.literacy_rate),
        "urban": clean(first.urban_pct),
        "dpi": series("dpi"),
        "rank": series("national_rank"),
        "srank": series("state_rank"),
        "upi": series("upi_value_per_capita_inr"),
        "bb": series("broadband_per_100"),
        "gst": series("gst_reg_per_1000"),
        "egov": series("egov_txn_per_capita"),
    })

# Monthly UPI value per state (the site sums states to get the national line).
upi = query("""
    SELECT s.state_name, t.year, t.month,
           SUM(f.txn_value_cr) AS value_cr, SUM(f.txn_count) AS txns
    FROM warehouse.fact_upi f
    JOIN warehouse.dim_time t USING (time_id)
    JOIN warehouse.dim_district d USING (district_id)
    JOIN warehouse.dim_state s USING (state_id)
    GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""")
months = sorted({(int(r.year), int(r.month)) for r in upi.itertuples()})
month_index = {m: i for i, m in enumerate(months)}
upi_by_state = {}
for r in upi.itertuples():
    slot = upi_by_state.setdefault(r.state_name, {"value_cr": [0] * len(months),
                                                  "txns": [0] * len(months)})
    i = month_index[(int(r.year), int(r.month))]
    slot["value_cr"][i] = clean(float(r.value_cr))
    slot["txns"][i] = int(r.txns)

audit = query("""
    SELECT source, rows_in, rows_loaded, errors_before, errors_after
    FROM warehouse.etl_audit
    WHERE run_at = (SELECT MAX(run_at) FROM warehouse.etl_audit)
    ORDER BY rows_in DESC""")
conn.close()

if not districts:
    raise SystemExit("No DPI rows found. Run the ETL and compute_dpi steps first.")

payload = {
    "meta": {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "simulated": True,
        "years": years,
        "districts": len(districts),
        "states": len({d["state"] for d in districts}),
    },
    "indicators": INDICATORS,
    "districts": districts,
    "upi": {"months": [f"{y}-{m:02d}" for y, m in months], "by_state": upi_by_state},
    "audit": [{k: clean(v) for k, v in row.items()} for row in audit.to_dict("records")],
}

target = OUT / "dashboard.json"
target.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
print(f"  dashboard.json  {len(districts):,} districts, {len(years)} years, "
      f"{target.stat().st_size / 1024:.0f} KB -> site/data/")
