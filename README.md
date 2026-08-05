# National Digital Economy Intelligence Warehouse

District-level analytical data warehouse in **PostgreSQL**, fed by **Python ETL
pipelines** that clean, normalize and integrate heterogeneous government-style
economic datasets, topped with a composite **District Prosperity Index (DPI)**
computed in SQL and **Power BI-ready exports**.

**Stack:** Python · PostgreSQL · SQL · pandas · RapidFuzz · psycopg2 · Power BI

## What it does

- Ingests **60,000+ rows** of district-level economic data across 5 heterogeneous
  national sources (UPI payments, broadband subscribers, GST registrations,
  e-governance transactions, demographics) covering **717 districts, 35 states/UTs**
  (real district registry; metric values simulated at realistic national magnitudes —
  see *Data provenance*).
- **ETL pipeline** (`scripts/etl_pipeline.py`): trims/normalizes text, parses 4+
  inconsistent date formats, coerces types, drops duplicates and impossible values,
  and resolves inconsistent district naming (`"Bellary"` → `"Ballari (Bellary)"`,
  `"Gurugram"` → `"Gurgaon"`, casing/whitespace/typos) via **RapidFuzz
  token-sort fuzzy matching**, state-scoped first, then national. Every run writes
  before/after error counts to an `etl_audit` table — the demo run eliminates
  **7,300+ error rows (100% of detectable errors)**.
- **Star schema** (`sql/schema.sql`): conformed `dim_district` / `dim_state` /
  `dim_time` dimensions with month, quarter and year grains; one fact table per source.
- **District Prosperity Index** (`sql/compute_dpi.sql`): weighted sum of
  min-max-normalized indicators, computed per district-year entirely in SQL
  (window functions + materialized view):

  | Weight | Indicator |
  |-------:|-----------|
  | 0.30 | UPI transaction value per capita |
  | 0.25 | Broadband subscribers per 100 people |
  | 0.20 | GST registrations per 1,000 people |
  | 0.15 | e-Gov transactions per capita |
  | 0.10 | Literacy rate |

  Plus `RANK()` for national and within-state rankings, a state summary view,
  and a year-over-year "top movers" view.
- **Power BI layer** (`scripts/export_powerbi.py` + `docs/POWERBI_SETUP.md`):
  11 clean star-schema CSVs ready to import, with modeling instructions for
  time-series and regional trend dashboards.

## Run it

```bash
# 1) Create and activate a local Python environment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 2) Run the ETL with your own PostgreSQL server
# create db `digital_economy`, then adjust the DSN in scripts/etl_pipeline.py if needed
./run_pipeline.sh

# 3) Or, for a zero-install local development setup on macOS ARM:
npm install @embedded-postgres/darwin-arm64
./run_pipeline.sh --with-postgres-embedded
```

Pipeline stages: `generate_raw_data.py` → `etl_pipeline.py` → `compute_dpi.sql` → `export_powerbi.py`.

## Project layout

```
data/reference/states_districts.json   real canonical district registry (722 entries)
data/raw/                              5 heterogeneous raw source CSVs (66k rows)
sql/schema.sql                         star schema DDL + ETL audit table
sql/compute_dpi.sql                    DPI materialized view + reporting views
scripts/generate_raw_data.py           raw source simulator (seeded, reproducible)
scripts/etl_pipeline.py                clean → fuzzy-resolve → load
scripts/export_powerbi.py              Power BI star-schema exports
exports/                               11 Power BI-ready CSVs
docs/POWERBI_SETUP.md                  dashboard modeling guide
```

## Data provenance

The district/state universe is real (community-maintained registry of official
Indian districts). Metric values are **synthetic but realistically calibrated**
(magnitudes and growth patterns modeled on public NPCI/TRAI/GSTN statistics),
generated with seeded randomness plus injected real-world data-quality problems
(alternate district names such as Prayagraj/Allahabad, mixed date formats, nulls,
duplicates, negative values) so the ETL layer has genuine work to do. To point the
pipeline at real bulk downloads (data.gov.in, RBI DBIE, TRAI), drop the files into
`data/raw/` and adjust the column mappings at the top of `etl_pipeline.py`.
