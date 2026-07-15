-- National Digital Economy Intelligence Warehouse
-- Star schema: conformed district & time dimensions, one fact table per source
DROP SCHEMA IF EXISTS warehouse CASCADE;
CREATE SCHEMA warehouse;
SET search_path TO warehouse;

CREATE TABLE dim_state (
    state_id    SERIAL PRIMARY KEY,
    state_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_district (
    district_id    SERIAL PRIMARY KEY,
    district_name  TEXT NOT NULL,
    state_id       INT NOT NULL REFERENCES dim_state,
    population     BIGINT,
    literacy_rate  NUMERIC(5,2),
    urban_pct      NUMERIC(5,2),
    UNIQUE (district_name, state_id)
);

CREATE TABLE dim_time (
    time_id   SERIAL PRIMARY KEY,
    year      INT NOT NULL,
    quarter   INT,          -- NULL for annual grain
    month     INT,          -- NULL for annual/quarterly grain
    grain     TEXT NOT NULL CHECK (grain IN ('month','quarter','year')),
    UNIQUE (year, quarter, month, grain)
);

CREATE TABLE fact_upi (
    district_id   INT NOT NULL REFERENCES dim_district,
    time_id       INT NOT NULL REFERENCES dim_time,
    txn_count     BIGINT,
    txn_value_cr  NUMERIC(14,2),
    PRIMARY KEY (district_id, time_id)
);

CREATE TABLE fact_broadband (
    district_id     INT NOT NULL REFERENCES dim_district,
    time_id         INT NOT NULL REFERENCES dim_time,
    broadband_subs  BIGINT,
    wireless_pct    NUMERIC(5,2),
    PRIMARY KEY (district_id, time_id)
);

CREATE TABLE fact_gst (
    district_id           INT NOT NULL REFERENCES dim_district,
    time_id               INT NOT NULL REFERENCES dim_time,
    gst_registrations     BIGINT,
    gst_returns_filed_pct NUMERIC(5,2),
    PRIMARY KEY (district_id, time_id)
);

CREATE TABLE fact_egov (
    district_id        INT NOT NULL REFERENCES dim_district,
    time_id            INT NOT NULL REFERENCES dim_time,
    egov_transactions  BIGINT,
    active_cscs        INT,
    PRIMARY KEY (district_id, time_id)
);

-- ETL run audit / data-quality metrics
CREATE TABLE etl_audit (
    run_at       TIMESTAMPTZ DEFAULT now(),
    source       TEXT,
    rows_in      INT,
    rows_loaded  INT,
    errors_before INT,
    errors_after  INT,
    notes        TEXT
);

CREATE INDEX idx_fact_upi_time ON fact_upi (time_id);
CREATE INDEX idx_fact_bb_time ON fact_broadband (time_id);
CREATE INDEX idx_fact_gst_time ON fact_gst (time_id);
CREATE INDEX idx_fact_egov_time ON fact_egov (time_id);
