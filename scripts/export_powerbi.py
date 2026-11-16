"""Export the warehouse as Power BI-ready star-schema CSVs."""
from pathlib import Path

import pandas as pd

from db import get_conn

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "exports"
OUT.mkdir(exist_ok=True)

EXPORTS = {
    "dim_district.csv": """
        SELECT d.district_id, d.district_name, s.state_name,
               d.population, d.literacy_rate, d.urban_pct
        FROM warehouse.dim_district d JOIN warehouse.dim_state s USING (state_id)""",
    "dim_time.csv": "SELECT * FROM warehouse.dim_time",
    "fact_upi_monthly.csv": """
        SELECT f.district_id, t.year, t.month, f.txn_count, f.txn_value_cr
        FROM warehouse.fact_upi f JOIN warehouse.dim_time t USING (time_id)""",
    "fact_broadband_quarterly.csv": """
        SELECT f.district_id, t.year, t.quarter, f.broadband_subs, f.wireless_pct
        FROM warehouse.fact_broadband f JOIN warehouse.dim_time t USING (time_id)""",
    "fact_gst_annual.csv": """
        SELECT f.district_id, t.year, f.gst_registrations, f.gst_returns_filed_pct
        FROM warehouse.fact_gst f JOIN warehouse.dim_time t USING (time_id)""",
    "fact_egov_annual.csv": """
        SELECT f.district_id, t.year, f.egov_transactions, f.active_cscs
        FROM warehouse.fact_egov f JOIN warehouse.dim_time t USING (time_id)""",
    "dpi_scores.csv": "SELECT * FROM warehouse.mv_dpi ORDER BY year, national_rank",
    "dpi_latest_rankings.csv": "SELECT * FROM warehouse.v_dpi_latest ORDER BY national_rank",
    "state_summary.csv": "SELECT * FROM warehouse.v_state_summary ORDER BY year, avg_dpi DESC",
    "dpi_top_movers.csv": "SELECT * FROM warehouse.v_dpi_movers LIMIT 100",
    "etl_audit.csv": "SELECT * FROM warehouse.etl_audit ORDER BY run_at",
}

conn = get_conn()
total = 0
for fname, sql in EXPORTS.items():
    df = pd.read_sql(sql, conn)
    df.to_csv(OUT / fname, index=False)
    total += len(df)
    print(f"  {fname:32s} {len(df):7,} rows")
print(f"\nExported {len(EXPORTS)} Power BI-ready files ({total:,} rows) to exports/")
conn.close()
