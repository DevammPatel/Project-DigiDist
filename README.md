# National Digital Economy Intelligence Warehouse

District-level analytical data warehouse in **PostgreSQL**, fed by **Python ETL
pipelines** that clean, normalize and integrate heterogeneous government-style
economic datasets, topped with a composite **District Prosperity Index (DPI)**
computed in SQL, a **public dashboard website** and **Power BI-ready exports**.

**Stack:** Python · PostgreSQL · SQL · pandas · RapidFuzz · psycopg2 · plain HTML/CSS/JS · GitHub Pages · Power BI

**Live site:** https://devammpatel.github.io/Project-DigiDist/ (published by GitHub
Actions from `main`; available once GitHub Pages is switched on for the repository).
All metric values on it are simulated, see *Data provenance*.

## What it does

- Ingests **60,000+ rows** of district-level economic data across 5 heterogeneous
  national sources (UPI payments, broadband subscribers, GST registrations,
  e-governance transactions, demographics) covering **722 districts, 35 states/UTs**
  (real district registry; metric values simulated at realistic national magnitudes —
  see *Data provenance*).
- **ETL pipeline** (`scripts/etl_pipeline.py`): trims/normalizes text, parses 4+
  inconsistent date formats, coerces types, drops duplicates and impossible values,
  and resolves inconsistent district naming in two steps: a reference list of
  official renames (`data/reference/district_aliases.json`, e.g. `"Gurugram"` →
  `"Gurgaon"`, `"Prayagraj"` → `"Allahabad"`), then **RapidFuzz token-sort fuzzy
  matching** for casing/whitespace/typos (`"Bellary"` → `"Ballari (Bellary)"`),
  state-scoped first, then national. A district is identified by name **and** state,
  so the five names that exist in two states (e.g. Aurangabad) stay separate. Every run writes
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
- **Website** (`site/` + `scripts/export_site.py`): a static dashboard with no server
  and no build step. The pipeline writes one JSON file (`site/data/dashboard.json`);
  the page reads it and draws the overview, sortable district rankings, state
  comparison, biggest rank movers, data-quality report and the scoring method.

## Run it

```bash
# 1) Create a local Python environment and install the pinned dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2a) Run against your own PostgreSQL server (the database is created if missing)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/digital_economy ./run_pipeline.sh

# 2b) Or use the bundled embedded PostgreSQL (no server to install)
npm install @embedded-postgres/darwin-arm64   # pick the package for your platform
./run_pipeline.sh --with-postgres-embedded

# 3) Open the website locally
python3 -m http.server 8000 --directory site   # then visit http://localhost:8000

# 4) Run the unit tests (no database needed)
.venv/bin/python -m unittest discover -s tests
```

Pipeline stages: `generate_raw_data.py` → `etl_pipeline.py` → `compute_dpi.py`
(runs `sql/compute_dpi.sql`) → `export_powerbi.py` → `export_site.py`.
Every script takes its connection from `DATABASE_URL` (see `scripts/db.py`).

## Deployment

`.github/workflows/deploy-site.yml` runs on every push to `main`: it starts a
temporary PostgreSQL, runs the tests and the full pipeline, and publishes `site/`
to GitHub Pages. Pull requests run the same steps without publishing. One-time
setup: in the repository settings, set **Pages → Source** to **GitHub Actions**.
Hosting and CI are free for public repositories.

## Project layout

```
data/reference/states_districts.json   real canonical district registry (722 entries)
data/reference/district_aliases.json   official renames and alternate spellings
data/raw/                              5 heterogeneous raw source CSVs (66k rows)
sql/schema.sql                         star schema DDL + ETL audit table
sql/compute_dpi.sql                    DPI materialized view + reporting views
scripts/generate_raw_data.py           raw source simulator (seeded, reproducible)
scripts/etl_pipeline.py                clean → fuzzy-resolve → load
scripts/compute_dpi.py                 runs sql/compute_dpi.sql
scripts/export_powerbi.py              Power BI star-schema exports
scripts/export_site.py                 writes site/data/dashboard.json for the website
scripts/db.py                          shared database connection (DATABASE_URL)
site/                                  static dashboard website (HTML, CSS, JS)
tests/                                 unit tests for the cleaning rules
.github/workflows/deploy-site.yml      test, run pipeline, publish to GitHub Pages
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
`data/raw/` and adjust the column mappings in `etl_pipeline.py`.
