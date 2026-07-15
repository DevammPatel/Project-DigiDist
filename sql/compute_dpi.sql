-- District Prosperity Index (DPI)
-- Composite, per district-year, from weighted min-max-normalized indicators:
--   0.30  UPI transaction value per capita        (digital payments depth)
--   0.25  broadband subscribers per 100 people    (connectivity)
--   0.20  GST registrations per 1000 people       (formal business activity)
--   0.15  e-gov transactions per capita           (digital public services)
--   0.10  literacy rate                           (human capital)
SET search_path TO warehouse;

DROP MATERIALIZED VIEW IF EXISTS mv_dpi CASCADE;

CREATE MATERIALIZED VIEW mv_dpi AS
WITH upi_yr AS (
    SELECT f.district_id, t.year,
           SUM(f.txn_value_cr) AS upi_value_cr,
           SUM(f.txn_count)    AS upi_txns
    FROM fact_upi f JOIN dim_time t USING (time_id)
    GROUP BY 1, 2
),
bb_yr AS (  -- year-end quarter as the annual figure
    SELECT DISTINCT ON (f.district_id, t.year)
           f.district_id, t.year, f.broadband_subs
    FROM fact_broadband f JOIN dim_time t USING (time_id)
    ORDER BY f.district_id, t.year, t.quarter DESC
),
base AS (
    SELECT d.district_id, d.district_name, s.state_name, u.year,
           d.population, d.literacy_rate, d.urban_pct,
           (u.upi_value_cr * 1e7) / NULLIF(d.population, 0)      AS upi_per_capita,
           (b.broadband_subs * 100.0) / NULLIF(d.population, 0)  AS bb_per_100,
           (g.gst_registrations * 1000.0) / NULLIF(d.population, 0) AS gst_per_1000,
           (e.egov_transactions * 1.0) / NULLIF(d.population, 0) AS egov_per_capita
    FROM upi_yr u
    JOIN dim_district d USING (district_id)
    JOIN dim_state s USING (state_id)
    LEFT JOIN bb_yr b USING (district_id, year)
    LEFT JOIN fact_gst g
        ON g.district_id = u.district_id
       AND g.time_id = (SELECT time_id FROM dim_time
                        WHERE year = u.year AND grain = 'year')
    LEFT JOIN fact_egov e
        ON e.district_id = u.district_id
       AND e.time_id = (SELECT time_id FROM dim_time
                        WHERE year = u.year AND grain = 'year')
),
normalized AS (
    SELECT *,
        (upi_per_capita  - MIN(upi_per_capita)  OVER w) / NULLIF(MAX(upi_per_capita)  OVER w - MIN(upi_per_capita)  OVER w, 0) AS n_upi,
        (bb_per_100      - MIN(bb_per_100)      OVER w) / NULLIF(MAX(bb_per_100)      OVER w - MIN(bb_per_100)      OVER w, 0) AS n_bb,
        (gst_per_1000    - MIN(gst_per_1000)    OVER w) / NULLIF(MAX(gst_per_1000)    OVER w - MIN(gst_per_1000)    OVER w, 0) AS n_gst,
        (egov_per_capita - MIN(egov_per_capita) OVER w) / NULLIF(MAX(egov_per_capita) OVER w - MIN(egov_per_capita) OVER w, 0) AS n_egov,
        (literacy_rate   - MIN(literacy_rate)   OVER w) / NULLIF(MAX(literacy_rate)   OVER w - MIN(literacy_rate)   OVER w, 0) AS n_lit
    FROM base
    WINDOW w AS (PARTITION BY year)
)
SELECT district_id, district_name, state_name, year,
       population, literacy_rate, urban_pct,
       ROUND(upi_per_capita::numeric, 2)  AS upi_value_per_capita_inr,
       ROUND(bb_per_100::numeric, 2)      AS broadband_per_100,
       ROUND(gst_per_1000::numeric, 2)    AS gst_reg_per_1000,
       ROUND(egov_per_capita::numeric, 2) AS egov_txn_per_capita,
       ROUND((100 * ( 0.30 * COALESCE(n_upi, 0)
                    + 0.25 * COALESCE(n_bb, 0)
                    + 0.20 * COALESCE(n_gst, 0)
                    + 0.15 * COALESCE(n_egov, 0)
                    + 0.10 * COALESCE(n_lit, 0)))::numeric, 2) AS dpi,
       RANK() OVER (PARTITION BY year ORDER BY
                    0.30 * COALESCE(n_upi, 0) + 0.25 * COALESCE(n_bb, 0)
                  + 0.20 * COALESCE(n_gst, 0) + 0.15 * COALESCE(n_egov, 0)
                  + 0.10 * COALESCE(n_lit, 0) DESC)             AS national_rank,
       RANK() OVER (PARTITION BY year, state_name ORDER BY
                    0.30 * COALESCE(n_upi, 0) + 0.25 * COALESCE(n_bb, 0)
                  + 0.20 * COALESCE(n_gst, 0) + 0.15 * COALESCE(n_egov, 0)
                  + 0.10 * COALESCE(n_lit, 0) DESC)             AS state_rank
FROM normalized;

CREATE UNIQUE INDEX ON mv_dpi (district_id, year);

-- Convenience views for reporting / Power BI
CREATE OR REPLACE VIEW v_dpi_latest AS
    SELECT * FROM mv_dpi WHERE year = (SELECT MAX(year) FROM mv_dpi);

CREATE OR REPLACE VIEW v_state_summary AS
    SELECT year, state_name,
           COUNT(*)               AS districts,
           ROUND(AVG(dpi), 2)     AS avg_dpi,
           MAX(dpi)               AS best_dpi,
           MIN(dpi)               AS worst_dpi
    FROM mv_dpi
    GROUP BY year, state_name;

CREATE OR REPLACE VIEW v_dpi_movers AS  -- biggest rank changes, latest vs prior year
    WITH latest AS (SELECT MAX(year) AS y FROM mv_dpi)
    SELECT c.district_name, c.state_name,
           p.national_rank AS rank_prev, c.national_rank AS rank_now,
           p.national_rank - c.national_rank AS places_gained
    FROM mv_dpi c
    JOIN latest l ON c.year = l.y
    JOIN mv_dpi p ON p.district_id = c.district_id AND p.year = l.y - 1
    ORDER BY places_gained DESC;
