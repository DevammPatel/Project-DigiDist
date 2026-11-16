"""
ETL pipeline: clean, normalize and integrate heterogeneous district-level
sources into the PostgreSQL star schema.

Steps per source:
  1. Extract      - read raw CSV
  2. Clean        - trim/normalize text, coerce types, drop impossible values,
                    dedupe, parse mixed date formats
  3. Resolve      - match inconsistent district names to the canonical registry:
                    exact name or known alias first, then fuzzy matching
                    (RapidFuzz token_sort_ratio, state-scoped first)
  4. Load         - upsert into warehouse facts via psycopg2 execute_values

Prints a data-quality report (error rows before vs after cleaning).
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values
from rapidfuzz import fuzz, process

from db import ensure_database, get_conn

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

FUZZY_THRESHOLD = 82

# ------------------------------------------------------------- canonical registry
registry = json.loads((ROOT / "data" / "reference" / "states_districts.json").read_text())
CANON = {}            # state -> [districts]
ALL_DISTRICTS = []    # (district, state)
for s in registry["states"]:
    CANON[s["state"]] = s["districts"]
    ALL_DISTRICTS += [(d, s["state"]) for d in s["districts"]]


def norm(s: str) -> str:
    """Basic text normalization applied before matching."""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("&amp;", "&")
    return s


def strip_paren(s: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", s).strip()


# Match against both full canonical names and their parenthetical-free forms,
# so "Bellary" hits "Ballari (Bellary)" and "Mysore" hits "Mysuru (Mysore)".
def build_choices(districts):
    choices = {}
    for d in districts:
        choices[d] = d
        bare = strip_paren(d)
        if bare != d:
            choices.setdefault(bare, d)
        for part in re.findall(r"\((.*?)\)", d):
            choices.setdefault(part.strip(), d)
    return choices


STATE_CHOICES = {st: build_choices(ds) for st, ds in CANON.items()}
GLOBAL_CHOICES = build_choices([d for d, _ in ALL_DISTRICTS])

unmatched = set()

STATE_CHOICES_LOWER = {st: {k.lower(): v for k, v in ch.items()}
                       for st, ch in STATE_CHOICES.items()}

# Official renames and transliterations that spelling similarity cannot catch
# ("Prayagraj" is Allahabad, "Trivandrum" is Thiruvananthapuram). Each alias is
# added as one more accepted name inside its own state.
for _entry in json.loads((ROOT / "data" / "reference" / "district_aliases.json").read_text()):
    for _alias in _entry["aliases"]:
        STATE_CHOICES_LOWER[_entry["state"]].setdefault(norm(_alias).lower(), _entry["district"])

STATE_LOOKUP = {st.lower(): st for st in CANON}

# Nation-wide lookup: name -> (district, state). A name that exists in more than
# one state (for example "Aurangabad" in Bihar and Maharashtra) is left out,
# because without a valid state there is no way to tell which one is meant.
_owners = {}
for _st, _choices in STATE_CHOICES_LOWER.items():
    for _name, _district in _choices.items():
        _owners.setdefault(_name, set()).add((_district, _st))
GLOBAL_PAIRS_LOWER = {name: next(iter(pairs)) for name, pairs in _owners.items()
                      if len(pairs) == 1}


@lru_cache(maxsize=100_000)
def resolve_district(raw_name: str, state: str):
    """Fuzzy-resolve a messy district name to its canonical (district, state) pair.

    Looks inside the row's state first; falls back to a stricter nation-wide
    search when the state is blank or wrong. Returns None when nothing matches.
    """
    name = norm(raw_name).lower()
    state = STATE_LOOKUP.get(norm(state).lower())
    if state:
        choices = STATE_CHOICES_LOWER[state]
        if name in choices:
            return choices[name], state
        hit = process.extractOne(name, choices.keys(), scorer=fuzz.token_sort_ratio,
                                 score_cutoff=FUZZY_THRESHOLD)
        if hit:
            return choices[hit[0]], state
    if name in GLOBAL_PAIRS_LOWER:
        return GLOBAL_PAIRS_LOWER[name]
    hit = process.extractOne(name, GLOBAL_PAIRS_LOWER.keys(), scorer=fuzz.token_sort_ratio,
                             score_cutoff=FUZZY_THRESHOLD + 5)
    if hit:
        return GLOBAL_PAIRS_LOWER[hit[0]]
    unmatched.add((raw_name, state))
    return None


def count_errors(df, dist_col, state_col, numeric_cols):
    """Rows with a data-quality problem: unknown district name, null/negative metric, duplicate."""
    canon_set = set(GLOBAL_CHOICES)
    bad_name = ~df[dist_col].astype(str).map(norm).isin(canon_set)
    bad_num = pd.Series(False, index=df.index)
    for c in numeric_cols:
        v = pd.to_numeric(df[c], errors="coerce")
        bad_num |= v.isna() | (v < 0)
    dupes = df.duplicated()
    return int((bad_name | bad_num | dupes).sum())


# ------------------------------------------------------------- time parsing
def parse_month(s):
    for fmt in ("%Y-%m", "%b-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return pd.to_datetime(str(s), format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.NaT


def parse_quarter(s):
    m = re.match(r"(\d{4})-?Q(\d)", str(s))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def parse_fy(s):
    m = re.match(r"(\d{4})", str(s))
    return int(m.group(1)) if m else None


# ------------------------------------------------------------- load helpers
def load_dimensions(cur, demo):
    cur.execute("INSERT INTO warehouse.dim_state (state_name) VALUES %s ON CONFLICT DO NOTHING"
                % ",".join(["('%s')" % st.replace("'", "''") for st in CANON]))
    cur.execute("SELECT state_name, state_id FROM warehouse.dim_state")
    state_ids = dict(cur.fetchall())

    rows = []
    for d, st in ALL_DISTRICTS:
        demo_row = demo.get((d, st), {})
        rows.append((d, state_ids[st], demo_row.get("population"),
                     demo_row.get("literacy_rate"), demo_row.get("urban_pct")))
    execute_values(cur, """
        INSERT INTO warehouse.dim_district (district_name, state_id, population, literacy_rate, urban_pct)
        VALUES %s ON CONFLICT (district_name, state_id) DO UPDATE
        SET population = EXCLUDED.population,
            literacy_rate = EXCLUDED.literacy_rate,
            urban_pct = EXCLUDED.urban_pct""", rows)
    cur.execute("""SELECT d.district_name, s.state_name, d.district_id
                   FROM warehouse.dim_district d JOIN warehouse.dim_state s USING (state_id)""")
    return {(dn, sn): did for dn, sn, did in cur.fetchall()}


def time_id_for(cur, cache, year, quarter=None, month=None, grain="year"):
    key = (year, quarter, month, grain)
    if key not in cache:
        cur.execute("""INSERT INTO warehouse.dim_time (year, quarter, month, grain)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (year, quarter, month, grain) DO UPDATE SET year = EXCLUDED.year
                       RETURNING time_id""", key)
        cache[key] = cur.fetchone()[0]
    return cache[key]


def audit(cur, source, rows_in, rows_loaded, before, after, notes=""):
    cur.execute("""INSERT INTO warehouse.etl_audit
                   (source, rows_in, rows_loaded, errors_before, errors_after, notes)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (source, rows_in, rows_loaded, before, after, notes))
    pct = 100 * (before - after) / before if before else 0
    print(f"  {source:38s} in={rows_in:6,}  loaded={rows_loaded:6,}  "
          f"errors {before:5,} -> {after:3,}  (-{pct:.0f}%)")


# A district is identified by name AND state: five names exist in two states.
DISTRICT_KEY = ["canonical_district", "canonical_state"]


def resolve_frame(df, dist_col, state_col):
    """Add canonical_district / canonical_state columns; drop unresolvable rows."""
    resolved = [resolve_district(n, s) for n, s in zip(df[dist_col].astype(str),
                                                       df[state_col].astype(str))]
    df = df.assign(canonical_district=[r[0] if r else None for r in resolved],
                   canonical_state=[r[1] if r else None for r in resolved])
    return df[df.canonical_district.notna()].copy()


def main():
    total_before = total_after = 0

    demo = pd.read_csv(RAW / "district_demographics.csv")
    demo_rows_in = len(demo)
    b = count_errors(demo, "district", "state", ["population", "literacy_rate"])
    demo = resolve_frame(demo, "district", "state")
    demo = demo.drop_duplicates(DISTRICT_KEY, keep="first")
    demo_map = demo.set_index(DISTRICT_KEY)[["population", "literacy_rate", "urban_pct"]] \
                   .to_dict("index")

    ensure_database()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(open(ROOT / "sql" / "schema.sql").read())
    district_ids = load_dimensions(cur, demo_map)
    tcache = {}

    def key(r):
        return district_ids[(r.canonical_district, r.canonical_state)]

    print("Data-quality report (error rows before -> after cleaning):")
    a = count_errors(demo.drop(columns=["district"]).rename(columns={"canonical_district": "district"}),
                     "district", "state", ["population", "literacy_rate"])
    audit(cur, "district_demographics.csv", demo_rows_in, len(demo_map), b, a)
    total_before += b; total_after += a

    # ---- UPI (monthly)
    upi = pd.read_csv(RAW / "upi_transactions_monthly.csv")
    n_in = len(upi)
    b = count_errors(upi, "district", "state", ["txn_count", "txn_value_cr"])
    upi["dt"] = upi["month"].map(parse_month)
    upi["txn_count"] = pd.to_numeric(upi.txn_count, errors="coerce")
    upi["txn_value_cr"] = pd.to_numeric(upi.txn_value_cr, errors="coerce")
    upi = upi[upi.dt.notna() & (upi.txn_count.fillna(0) >= 0)]
    upi = resolve_frame(upi, "district", "state")
    upi = upi.drop_duplicates(DISTRICT_KEY + ["dt"], keep="first")
    # impute remaining nulls with district median (documented, auditable choice)
    upi["txn_count"] = upi.groupby(DISTRICT_KEY)["txn_count"] \
                          .transform(lambda x: x.fillna(x.median()))
    upi["txn_value_cr"] = upi.groupby(DISTRICT_KEY)["txn_value_cr"] \
                             .transform(lambda x: x.fillna(x.median()))
    rows = [(key(r), time_id_for(cur, tcache, r.dt.year, (r.dt.month - 1) // 3 + 1, r.dt.month, "month"),
             int(r.txn_count), float(r.txn_value_cr)) for r in upi.itertuples()]
    execute_values(cur, """INSERT INTO warehouse.fact_upi VALUES %s
                           ON CONFLICT (district_id, time_id) DO NOTHING""", rows, page_size=5000)
    a = count_errors(upi.drop(columns=["district"]).rename(columns={"canonical_district": "district"}),
                     "district", "state", ["txn_count", "txn_value_cr"])
    audit(cur, "upi_transactions_monthly.csv", n_in, len(rows), b, a)
    total_before += b; total_after += a

    # ---- Broadband (quarterly)
    bb = pd.read_csv(RAW / "broadband_subscribers_quarterly.csv")
    n_in = len(bb)
    b = count_errors(bb, "district_name", "state_name", ["broadband_subs"])
    bb[["yr", "q"]] = bb["quarter"].map(parse_quarter).tolist()
    bb["broadband_subs"] = pd.to_numeric(bb.broadband_subs, errors="coerce")
    bb = bb[bb.yr.notna()]
    bb = resolve_frame(bb, "district_name", "state_name")
    bb = bb.drop_duplicates(DISTRICT_KEY + ["yr", "q"], keep="first")
    bb["broadband_subs"] = bb.groupby(DISTRICT_KEY)["broadband_subs"] \
                             .transform(lambda x: x.fillna(x.median()))
    rows = [(key(r), time_id_for(cur, tcache, int(r.yr), int(r.q), None, "quarter"),
             int(r.broadband_subs), float(r.wireless_pct)) for r in bb.itertuples()]
    execute_values(cur, """INSERT INTO warehouse.fact_broadband VALUES %s
                           ON CONFLICT (district_id, time_id) DO NOTHING""", rows, page_size=5000)
    a = count_errors(bb.drop(columns=["district_name"]).rename(columns={"canonical_district": "district_name"}),
                     "district_name", "state_name", ["broadband_subs"])
    audit(cur, "broadband_subscribers_quarterly.csv", n_in, len(rows), b, a)
    total_before += b; total_after += a

    # ---- GST (annual)
    gst = pd.read_csv(RAW / "gst_registrations_annual.csv")
    n_in = len(gst)
    b = count_errors(gst, "district", "state", ["gst_registrations", "gst_returns_filed_pct"])
    gst["yr"] = gst["fin_year"].map(parse_fy)
    gst["gst_returns_filed_pct"] = pd.to_numeric(gst.gst_returns_filed_pct, errors="coerce")
    gst = resolve_frame(gst, "district", "state")
    gst = gst.drop_duplicates(DISTRICT_KEY + ["yr"], keep="first")
    gst["gst_returns_filed_pct"] = gst.groupby(DISTRICT_KEY)["gst_returns_filed_pct"] \
                                      .transform(lambda x: x.fillna(x.median()))
    rows = [(key(r), time_id_for(cur, tcache, int(r.yr), None, None, "year"),
             int(r.gst_registrations), float(r.gst_returns_filed_pct)) for r in gst.itertuples()]
    execute_values(cur, """INSERT INTO warehouse.fact_gst VALUES %s
                           ON CONFLICT (district_id, time_id) DO NOTHING""", rows, page_size=5000)
    a = count_errors(gst.drop(columns=["district"]).rename(columns={"canonical_district": "district"}),
                     "district", "state", ["gst_registrations", "gst_returns_filed_pct"])
    audit(cur, "gst_registrations_annual.csv", n_in, len(rows), b, a)
    total_before += b; total_after += a

    # ---- e-Gov (annual)
    eg = pd.read_csv(RAW / "csc_egov_annual.csv")
    n_in = len(eg)
    b = count_errors(eg, "District Name", "State/UT", ["egov_transactions", "active_cscs"])
    eg = resolve_frame(eg, "District Name", "State/UT")
    eg = eg.drop_duplicates(DISTRICT_KEY + ["year"], keep="first")
    rows = [(key(r), time_id_for(cur, tcache, int(r.year), None, None, "year"),
             int(r.egov_transactions), int(r.active_cscs)) for r in eg.itertuples()]
    execute_values(cur, """INSERT INTO warehouse.fact_egov VALUES %s
                           ON CONFLICT (district_id, time_id) DO NOTHING""", rows, page_size=5000)
    a = count_errors(eg.drop(columns=["District Name"]).rename(columns={"canonical_district": "District Name"}),
                     "District Name", "State/UT", ["egov_transactions", "active_cscs"])
    audit(cur, "csc_egov_annual.csv", n_in, len(rows), b, a)
    total_before += b; total_after += a

    conn.commit()
    pct = 100 * (total_before - total_after) / total_before if total_before else 0
    print(f"\nTOTAL error rows: {total_before:,} -> {total_after:,}  "
          f"({pct:.1f}% reduction in data errors)")
    if unmatched:
        print(f"Unresolvable district names quarantined: {len(unmatched)} "
              f"(e.g. {sorted(unmatched)[:3]})")

    cur.execute("SELECT count(*) FROM warehouse.fact_upi")
    print(f"fact_upi rows: {cur.fetchone()[0]:,}")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
