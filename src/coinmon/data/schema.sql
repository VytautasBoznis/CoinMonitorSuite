-- CoinMonitorSuite scraper schema. Idempotent: safe to run on every startup.
-- Requires the TimescaleDB extension (present in the timescale/timescaledb images).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Preprocessed, query-ready candles. One row per (exchange, symbol, timeframe, bar).
-- open_time is the bar's open timestamp in epoch milliseconds (UTC).
CREATE TABLE IF NOT EXISTS candles (
    exchange   TEXT             NOT NULL,
    symbol     TEXT             NOT NULL,
    timeframe  TEXT             NOT NULL,
    open_time  BIGINT           NOT NULL,
    open       DOUBLE PRECISION NOT NULL,
    high       DOUBLE PRECISION NOT NULL,
    low        DOUBLE PRECISION NOT NULL,
    close      DOUBLE PRECISION NOT NULL,
    volume     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (exchange, symbol, timeframe, open_time)
);

-- Partition by open_time so range scans / retention scale (BIGINT epoch-ms partitioning).
SELECT create_hypertable(
    'candles', 'open_time',
    chunk_time_interval => 2592000000,  -- 30 days in ms
    if_not_exists => TRUE
);

-- Append-only archive of the original exchange payloads, untouched, for provenance/replay.
CREATE TABLE IF NOT EXISTS raw_candles (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exchange        TEXT   NOT NULL,
    symbol          TEXT   NOT NULL,
    timeframe       TEXT   NOT NULL,
    fetched_at      BIGINT NOT NULL,
    open_time_start BIGINT,
    open_time_end   BIGINT,
    payload         JSONB  NOT NULL
);

CREATE INDEX IF NOT EXISTS raw_candles_series_idx
    ON raw_candles (exchange, symbol, timeframe, fetched_at);

-- Perp funding-rate history (chunk T; feeds the W3 carry family). One row per settlement.
-- symbol is the perp's unified form, e.g. BTC/USDC:USDC; funding_time is the settlement
-- timestamp in epoch milliseconds (UTC). Data-only — no trading implications.
CREATE TABLE IF NOT EXISTS funding_rates (
    exchange     TEXT             NOT NULL,
    symbol       TEXT             NOT NULL,
    funding_time BIGINT           NOT NULL,
    rate         DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (exchange, symbol, funding_time)
);

SELECT create_hypertable(
    'funding_rates', 'funding_time',
    chunk_time_interval => 7776000000,  -- 90 days in ms (funding settles every 8h)
    if_not_exists => TRUE
);

-- Perp open-interest history (Plan-B P2 positioning signal; Bybit retains ~400+ daily points).
-- One row per (exchange, symbol, timeframe, bar). ts is the interval's timestamp in epoch ms (UTC);
-- oi_amount is open interest in BASE-currency contracts (Bybit's openInterest). Data-only.
CREATE TABLE IF NOT EXISTS open_interest (
    exchange   TEXT             NOT NULL,
    symbol     TEXT             NOT NULL,
    timeframe  TEXT             NOT NULL,
    ts         BIGINT           NOT NULL,
    oi_amount  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (exchange, symbol, timeframe, ts)
);

SELECT create_hypertable(
    'open_interest', 'ts',
    chunk_time_interval => 2592000000,  -- 30 days in ms
    if_not_exists => TRUE
);
