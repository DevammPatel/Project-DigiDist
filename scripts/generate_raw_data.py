"""
Generate heterogeneous 'raw' government-style source datasets for the
National Digital Economy Intelligence Warehouse.

District universe is REAL (722 districts across 35 states/UTs, from a
community-maintained registry of official Indian districts). Metric values are
synthetic but calibrated to realistic national magnitudes (UPI/TRAI/GST-style),
because bulk downloads from data.gov.in / RBI are not possible in this
environment.

Injects realistic data-quality problems for the ETL to resolve:
  - inconsistent district naming (alt spellings, dropped parentheticals,
    casing, stray whitespace, typos)
  - mixed date formats across sources
  - missing values, duplicate rows, impossible values (negatives/outliers)
"""
import json
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

registry = json.loads((ROOT / "data" / "reference" / "states_districts.json").read_text())
DISTRICTS = [(d, s["state"]) for s in registry["states"] for d in s["districts"]]

# Well-known alternate names (old name <-> new name, transliteration variants).
# Kept in a reference file because the ETL uses the same list to resolve them.
ALT_NAMES = {(e["district"], e["state"]): e["aliases"]
             for e in json.loads((ROOT / "data" / "reference" / "district_aliases.json").read_text())}


def messy_name(canonical: str, state: str) -> str:
    """Return a realistically inconsistent rendering of a district name."""
    r = random.random()
    if (canonical, state) in ALT_NAMES and r < 0.55:
        return random.choice(ALT_NAMES[(canonical, state)])
    if r < 0.62 and "(" in canonical:                     # drop parenthetical
        return re.sub(r"\s*\(.*?\)", "", canonical).strip()
    if r < 0.72:                                          # casing chaos
        return canonical.upper() if r < 0.67 else canonical.lower()
    if r < 0.82:                                          # stray whitespace
        return "  " + canonical + " " if r < 0.77 else canonical.replace(" ", "  ")
    if r < 0.87 and len(canonical) > 6:                   # single-char typo
        i = random.randrange(1, len(canonical) - 1)
        return canonical[:i] + canonical[i + 1:]
    return canonical


def maybe_messy(canonical: str, state: str, p: float = 0.10) -> str:
    return messy_name(canonical, state) if random.random() < p else canonical


# District 'development level' drives all metrics so sources correlate sensibly
# Keyed by (district, state): five district names exist in two states.
base_level = {key: np.clip(np.random.lognormal(0, 0.6), 0.15, 8.0) for key in DISTRICTS}
population = {key: int(np.clip(np.random.lognormal(14.2, 0.75), 60_000, 12_000_000))
              for key in DISTRICTS}

MONTH_FORMATS = ["%Y-%m", "%b-%Y", "%d/%m/%Y", "%Y/%m/%d"]

# ---------------------------------------------------------------- source 1
# NPCI-style UPI transactions, monthly 2021-2025
rows = []
months = pd.period_range("2021-01", "2025-12", freq="M")
for d, s in DISTRICTS:
    lvl = base_level[(d, s)]
    pop = population[(d, s)]
    for i, m in enumerate(months):
        growth = (1.035 + 0.01 * min(lvl, 3)) ** i          # digital adoption curve
        txn = pop * 0.9 * lvl * growth / 60 * np.random.lognormal(0, 0.12)
        val = txn * np.random.uniform(1400, 2100) / 1e7     # crore INR
        fmt = random.choice(MONTH_FORMATS)
        rows.append({
            "month": m.to_timestamp().strftime(fmt),
            "district": maybe_messy(d, s, 0.12),
            "state": s if random.random() > 0.03 else s.upper(),
            "txn_count": int(txn) if random.random() > 0.015 else None,
            "txn_value_cr": round(val, 2) if random.random() > 0.012 else None,
        })
upi = pd.DataFrame(rows)
dup = upi.sample(frac=0.006, random_state=1)                    # duplicates
neg = upi.sample(frac=0.003, random_state=2).assign(txn_count=lambda x: -x["txn_count"].fillna(1000))
upi = pd.concat([upi, dup, neg], ignore_index=True).sample(frac=1, random_state=3)
upi.to_csv(RAW / "upi_transactions_monthly.csv", index=False)

# ---------------------------------------------------------------- source 2
# TRAI-style broadband subscribers, quarterly
rows = []
quarters = pd.period_range("2021Q1", "2025Q4", freq="Q")
for d, s in DISTRICTS:
    lvl, pop = base_level[(d, s)], population[(d, s)]
    for i, q in enumerate(quarters):
        subs = pop * (0.18 + 0.03 * min(lvl, 4)) * (1.03 ** i) * np.random.lognormal(0, 0.08)
        rows.append({
            "quarter": str(q) if random.random() > 0.3 else f"{q.year}-Q{q.quarter}",
            "district_name": maybe_messy(d, s, 0.10),
            "state_name": s,
            "broadband_subs": int(subs) if random.random() > 0.01 else "",
            "wireless_pct": round(np.random.uniform(88, 99), 1),
        })
bb = pd.DataFrame(rows)
bb = pd.concat([bb, bb.sample(frac=0.004, random_state=4)], ignore_index=True)
bb.to_csv(RAW / "broadband_subscribers_quarterly.csv", index=False)

# ---------------------------------------------------------------- source 3
# GSTN-style registrations, annual
rows = []
for d, s in DISTRICTS:
    lvl, pop = base_level[(d, s)], population[(d, s)]
    for yr in range(2021, 2026):
        reg = pop / 1000 * (2.5 + 1.8 * min(lvl, 4)) * (1.06 ** (yr - 2021)) * np.random.lognormal(0, 0.10)
        rows.append({
            "fin_year": f"{yr}-{str(yr + 1)[2:]}" if random.random() > 0.25 else str(yr),
            "district": maybe_messy(d, s, 0.11),
            "state": s,
            "gst_registrations": int(reg),
            "gst_returns_filed_pct": round(np.random.uniform(55, 96), 1) if random.random() > 0.02 else None,
        })
pd.DataFrame(rows).to_csv(RAW / "gst_registrations_annual.csv", index=False)

# ---------------------------------------------------------------- source 4
# CSC / e-governance service transactions, annual
rows = []
for d, s in DISTRICTS:
    lvl, pop = base_level[(d, s)], population[(d, s)]
    for yr in range(2021, 2026):
        tx = pop * (0.4 + 0.15 * min(lvl, 3)) * (1.08 ** (yr - 2021)) * np.random.lognormal(0, 0.15)
        rows.append({
            "year": yr,
            "District Name": maybe_messy(d, s, 0.13),
            "State/UT": s,
            "egov_transactions": int(tx),
            "active_cscs": int(pop / 6000 * np.random.uniform(0.6, 1.4)),
        })
pd.DataFrame(rows).to_csv(RAW / "csc_egov_annual.csv", index=False)

# ---------------------------------------------------------------- source 5
# Census-style district demographics (static)
rows = []
for d, s in DISTRICTS:
    lvl, pop = base_level[(d, s)], population[(d, s)]
    rows.append({
        "district": maybe_messy(d, s, 0.08),
        "state": s,
        "population": pop,
        "literacy_rate": round(np.clip(58 + 8 * np.log1p(lvl) + np.random.normal(0, 5), 38, 97), 1),
        "urban_pct": round(np.clip(12 + 14 * np.log1p(lvl) + np.random.normal(0, 8), 3, 100), 1),
    })
pd.DataFrame(rows).to_csv(RAW / "district_demographics.csv", index=False)

total = sum(len(pd.read_csv(f, low_memory=False)) for f in RAW.glob("*.csv"))
print(f"Generated {len(list(RAW.glob('*.csv')))} raw source files, {total:,} total rows")
