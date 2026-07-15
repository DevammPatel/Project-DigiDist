# Power BI Dashboard Setup

The `exports/` folder is a ready-to-import star schema.

## 1. Import

Get Data → Text/CSV → import all 11 files from `exports/`.

## 2. Model (Model view)

Create one-to-many relationships (single direction, dimension → fact):

- `dim_district[district_id]` → `fact_upi_monthly`, `fact_broadband_quarterly`,
  `fact_gst_annual`, `fact_egov_annual`, `dpi_scores` (each on `district_id`)
- `dpi_scores` already contains `district_name`, `state_name`, `year` — usable standalone.

Create a proper date column for time series (Power Query, fact_upi_monthly):

```
Date = #date([year], [month], 1)
```

Mark a Date table if you want time-intelligence DAX (YTD, YoY%).

## 3. Suggested measures (DAX)

```dax
Total UPI Value (Cr) = SUM(fact_upi_monthly[txn_value_cr])
UPI YoY % =
VAR prev = CALCULATE([Total UPI Value (Cr)], DATEADD('Date'[Date], -1, YEAR))
RETURN DIVIDE([Total UPI Value (Cr)] - prev, prev)
Avg DPI = AVERAGE(dpi_scores[dpi])
Best Rank = MIN(dpi_scores[national_rank])
```

## 4. Report pages

1. **National overview** — Card visuals (total UPI value, districts covered, avg DPI),
   line chart of monthly UPI value, filled map of India by state avg DPI.
2. **District rankings** — table of `dpi_latest_rankings` with conditional
   formatting on `dpi`; bar chart of top/bottom 20; slicer on `state_name`.
3. **Regional trends** — `state_summary` line chart of `avg_dpi` by year;
   matrix state × year heat map.
4. **Movers** — `dpi_top_movers` bar chart of `places_gained`.
5. **Data quality** — `etl_audit` table: rows in/loaded, errors before → after per source.

## 5. Refresh

Re-run `./run_pipeline.sh`, then Refresh in Power BI — file paths stay stable.
