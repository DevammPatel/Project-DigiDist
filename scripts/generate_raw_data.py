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

# Well-known alternate names (old name <-> new name, transliteration variants)
ALT_NAMES = {
    "Bengaluru (Bangalore) Urban": ["Bangalore Urban", "Bengaluru Urban", "BANGALORE"],
    "Bengaluru (Bangalore) Rural": ["Bangalore Rural", "Bengaluru Rural"],
    "Mysuru (Mysore)": ["Mysore", "Mysuru"],
    "Belagavi (Belgaum)": ["Belgaum", "Belagavi"],
    "Kalaburagi (Gulbarga)": ["Gulbarga"],
    "Allahabad": ["Prayagraj", "ALLAHABAD"],
    "Gurgaon": ["Gurugram", "GURGAON"],
    "Mewat": ["Nuh"],
    "Faizabad": ["Ayodhya"],
    "Hoshangabad": ["Narmadapuram"],
    "Aurangabad": ["Chhatrapati Sambhajinagar", "Aurangabad (MH)"],
    "Osmanabad": ["Dharashiv"],
    "Burdwan (Bardhaman)": ["Bardhaman", "Purba Bardhaman"],
    "Purnia (Purnea)": ["Purnea", "Purnia"],
    "Munger (Monghyr)": ["Monghyr", "Munger"],
    "East Champaran (Motihari)": ["Purbi Champaran", "East Champaran"],
    "Kaimur (Bhabua)": ["Bhabua", "Kaimur"],
    "Thoothukudi (Tuticorin)": ["Tuticorin", "Thoothukudi"],
    "Tiruchirappalli": ["Trichy", "Tiruchirapalli"],
    "Kanchipuram": ["Kancheepuram"],
    "Viluppuram": ["Villupuram"],
    "Kachchh": ["Kutch", "Kachchh (Bhuj)"],
    "Banaskantha (Palanpur)": ["Banaskantha", "Banas Kantha"],
    "Sabarkantha (Himmatnagar)": ["Sabarkantha", "Sabar Kantha"],
    "Panchmahal (Godhra)": ["Panchmahals", "Panch Mahals"],
    "Dangs (Ahwa)": ["The Dangs", "Dang"],
    "Kheda (Nadiad)": ["Kheda"],
    "Ahmedabad": ["Ahmadabad"],
    "Vadodara": ["Baroda", "VADODARA"],
    "YSR Kadapa": ["Cuddapah", "Y.S.R. Kadapa", "Kadapa"],
    "Nellore": ["Sri Potti Sriramulu Nellore", "SPSR Nellore"],
    "Visakhapatnam": ["Vishakhapatnam", "Vizag"],
    "Kendujhar (Keonjhar)": ["Keonjhar", "Kendujhar"],
    "Balasore": ["Baleshwar", "Baleswar"],
    "Sonepur": ["Subarnapur", "Sonapur"],
    "Khordha": ["Khurda", "Khordha (Bhubaneswar)"],
    "Sahibzada Ajit Singh Nagar (Mohali)": ["Mohali", "SAS Nagar", "S.A.S. Nagar"],
    "Nawanshahr (Shahid Bhagat Singh Nagar)": ["Nawanshahr", "SBS Nagar", "Shaheed Bhagat Singh Nagar"],
    "Muktsar": ["Sri Muktsar Sahib"],
    "Ferozepur": ["Firozpur"],
    "Amroha (J.P. Nagar)": ["Amroha", "Jyotiba Phule Nagar", "J P Nagar"],
    "Hapur (Panchsheel Nagar)": ["Hapur", "Panchsheel Nagar"],
    "Kanshiram Nagar (Kasganj)": ["Kasganj", "Kanshiram Nagar"],
    "Sambhal (Bhim Nagar)": ["Sambhal", "Bhim Nagar"],
    "Shamali (Prabuddh Nagar)": ["Shamli", "Prabuddh Nagar"],
    "Amethi (Chatrapati Sahuji Mahraj Nagar)": ["Amethi", "CSM Nagar"],
    "Kushinagar (Padrauna)": ["Kushinagar", "Padrauna"],
    "Lakhimpur - Kheri": ["Lakhimpur Kheri", "Kheri", "Lakhimpur-Kheri"],
    "RaeBareli": ["Rae Bareli", "Raebareli", "Rai Bareilly"],
    "Gautam Buddha Nagar": ["Gautam Budh Nagar", "G.B. Nagar", "Noida"],
    "Bhadohi": ["Sant Ravidas Nagar", "Sant Ravidas Nagar (Bhadohi)"],
    "Kamrup Metropolitan": ["Kamrup (Metro)", "Kamrup Metro"],
    "Dima Hasao": ["North Cachar Hills"],
    "Sivasagar": ["Sibsagar"],
    "Dakshin Dinajpur (South Dinajpur)": ["Dakshin Dinajpur", "South Dinajpur"],
    "Uttar Dinajpur (North Dinajpur)": ["Uttar Dinajpur", "North Dinajpur"],
    "Paschim Medinipur (West Medinipur)": ["Paschim Medinipur", "West Midnapore", "West Medinipur"],
    "Purba Medinipur (East Medinipur)": ["Purba Medinipur", "East Midnapore", "East Medinipur"],
    "Cooch Behar": ["Koch Bihar", "Coochbehar"],
    "Hooghly": ["Hugli", "Hooghly (Chinsurah)"],
    "Howrah": ["Haora"],
    "North 24 Parganas": ["North Twenty Four Parganas", "24 Parganas (N)"],
    "South 24 Parganas": ["South Twenty Four Parganas", "24 Parganas (S)"],
    "Dantewada (South Bastar)": ["Dantewada", "South Bastar Dantewada"],
    "Kanker (North Bastar)": ["Kanker", "Uttar Bastar Kanker"],
    "Kabirdham (Kawardha)": ["Kabirdham", "Kawardha"],
    "Korea (Koriya)": ["Koriya", "Korea"],
    "Sirmaur (Sirmour)": ["Sirmaur", "Sirmour"],
    "Lahaul & Spiti": ["Lahul and Spiti", "Lahaul and Spiti"],
    "Mumbai City": ["Mumbai", "Greater Mumbai"],
    "Ahmednagar": ["Ahmadnagar", "Ahilyanagar"],
    "Beed": ["Bid"],
    "Buldhana": ["Buldana"],
    "Raigad": ["Raigarh (MH)", "Raigad (Alibag)"],
    "Pondicherry": ["Puducherry"],
    "Ballari (Bellary)": ["Bellary", "Ballari"],
    "Shivamogga (Shimoga)": ["Shimoga", "Shivamogga"],
    "Tumakuru (Tumkur)": ["Tumkur", "Tumakuru"],
    "Chikkamagaluru (Chikmagalur)": ["Chikmagalur", "Chikkamagaluru"],
    "Vijayapura (Bijapur)": ["Bijapur (KA)", "Vijayapura"],
    "Uttara Kannada (Karwar)": ["Uttara Kannada", "North Kanara", "Karwar"],
    "Kozhikode": ["Calicut"],
    "Thiruvananthapuram": ["Trivandrum"],
    "Alappuzha": ["Alleppey"],
    "Kollam": ["Quilon"],
    "Kannur": ["Cannanore"],
    "Thrissur": ["Trichur"],
    "Warangal (Urban)": ["Warangal Urban", "Warangal"],
    "Warangal (Rural)": ["Warangal Rural"],
    "Medchal": ["Medchal-Malkajgiri", "Medchal Malkajgiri"],
    "Rangareddy": ["Ranga Reddy", "K.V. Rangareddy"],
    "Hazaribag": ["Hazaribagh"],
    "Palamu": ["Palamau"],
    "Sri Ganganagar": ["Ganganagar", "Sriganganagar"],
    "Jalore": ["Jalor"],
    "Jhunjhunu": ["Jhunjhunun"],
    "Chittoor": ["Chittor", "Chitoor"],
    "Kurnool": ["Karnul"],
    "Bandipore": ["Bandipora"],
    "Baramulla": ["Baramula"],
    "Budgam": ["Badgam"],
    "Shopian": ["Shupiyan"],
    "Leh": ["Leh (Ladakh)", "Leh Ladakh"],
}


def messy_name(canonical: str) -> str:
    """Return a realistically inconsistent rendering of a district name."""
    r = random.random()
    if canonical in ALT_NAMES and r < 0.55:
        return random.choice(ALT_NAMES[canonical])
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


def maybe_messy(canonical: str, p: float = 0.10) -> str:
    return messy_name(canonical) if random.random() < p else canonical


# District 'development level' drives all metrics so sources correlate sensibly
base_level = {d: np.clip(np.random.lognormal(0, 0.6), 0.15, 8.0) for d, _ in DISTRICTS}
population = {d: int(np.clip(np.random.lognormal(14.2, 0.75), 60_000, 12_000_000))
              for d, _ in DISTRICTS}

MONTH_FORMATS = ["%Y-%m", "%b-%Y", "%d/%m/%Y", "%Y/%m/%d"]

# ---------------------------------------------------------------- source 1
# NPCI-style UPI transactions, monthly 2021-2025
rows = []
months = pd.period_range("2021-01", "2025-12", freq="M")
for d, s in DISTRICTS:
    lvl = base_level[d]
    pop = population[d]
    for i, m in enumerate(months):
        growth = (1.035 + 0.01 * min(lvl, 3)) ** i          # digital adoption curve
        txn = pop * 0.9 * lvl * growth / 60 * np.random.lognormal(0, 0.12)
        val = txn * np.random.uniform(1400, 2100) / 1e7     # crore INR
        fmt = random.choice(MONTH_FORMATS)
        rows.append({
            "month": m.to_timestamp().strftime(fmt),
            "district": maybe_messy(d, 0.12),
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
    lvl, pop = base_level[d], population[d]
    for i, q in enumerate(quarters):
        subs = pop * (0.18 + 0.03 * min(lvl, 4)) * (1.03 ** i) * np.random.lognormal(0, 0.08)
        rows.append({
            "quarter": str(q) if random.random() > 0.3 else f"{q.year}-Q{q.quarter}",
            "district_name": maybe_messy(d, 0.10),
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
    lvl, pop = base_level[d], population[d]
    for yr in range(2021, 2026):
        reg = pop / 1000 * (2.5 + 1.8 * min(lvl, 4)) * (1.06 ** (yr - 2021)) * np.random.lognormal(0, 0.10)
        rows.append({
            "fin_year": f"{yr}-{str(yr + 1)[2:]}" if random.random() > 0.25 else str(yr),
            "district": maybe_messy(d, 0.11),
            "state": s,
            "gst_registrations": int(reg),
            "gst_returns_filed_pct": round(np.random.uniform(55, 96), 1) if random.random() > 0.02 else None,
        })
pd.DataFrame(rows).to_csv(RAW / "gst_registrations_annual.csv", index=False)

# ---------------------------------------------------------------- source 4
# CSC / e-governance service transactions, annual
rows = []
for d, s in DISTRICTS:
    lvl, pop = base_level[d], population[d]
    for yr in range(2021, 2026):
        tx = pop * (0.4 + 0.15 * min(lvl, 3)) * (1.08 ** (yr - 2021)) * np.random.lognormal(0, 0.15)
        rows.append({
            "year": yr,
            "District Name": maybe_messy(d, 0.13),
            "State/UT": s,
            "egov_transactions": int(tx),
            "active_cscs": int(pop / 6000 * np.random.uniform(0.6, 1.4)),
        })
pd.DataFrame(rows).to_csv(RAW / "csc_egov_annual.csv", index=False)

# ---------------------------------------------------------------- source 5
# Census-style district demographics (static)
rows = []
for d, s in DISTRICTS:
    lvl, pop = base_level[d], population[d]
    rows.append({
        "district": maybe_messy(d, 0.08),
        "state": s,
        "population": pop,
        "literacy_rate": round(np.clip(58 + 8 * np.log1p(lvl) + np.random.normal(0, 5), 38, 97), 1),
        "urban_pct": round(np.clip(12 + 14 * np.log1p(lvl) + np.random.normal(0, 8), 3, 100), 1),
    })
pd.DataFrame(rows).to_csv(RAW / "district_demographics.csv", index=False)

total = sum(len(pd.read_csv(f, low_memory=False)) for f in RAW.glob("*.csv"))
print(f"Generated {len(list(RAW.glob('*.csv')))} raw source files, {total:,} total rows")
