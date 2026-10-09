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

-- Perp liquidation prints from Bybit's v5 public allLiquidation websocket (idea-8 cascade
-- research). Bybit serves NO liquidation history, so this holds only what a running collector
-- saw: always read it together with liquidation_coverage. ts is Bybit's T (epoch ms UTC); side is
-- Bybit's S verbatim: the LIQUIDATED POSITION's side, so 'Buy' = a long was liquidated = forced
-- selling (checked on the first live sample: every 'Buy' print's price sat below the 1m close);
-- price is the bankruptcy price; size is in base-currency contracts; recv_ms is when the collector
-- got the push (feed-latency diagnostics). Natural key, so separate collectors stitch by upsert-merge.
CREATE TABLE IF NOT EXISTS liquidations (
    exchange  TEXT             NOT NULL,
    symbol    TEXT             NOT NULL,
    ts        BIGINT           NOT NULL,
    side      TEXT             NOT NULL,
    price     DOUBLE PRECISION NOT NULL,
    size      DOUBLE PRECISION NOT NULL,
    recv_ms   BIGINT           NOT NULL,
    PRIMARY KEY (exchange, symbol, ts, side, price, size)
);

SELECT create_hypertable(
    'liquidations', 'ts',
    chunk_time_interval => 604800000,  -- 7 days in ms (cascade days are dense)
    if_not_exists => TRUE
);

-- Per-symbol windows [start_ms, end_ms] during which a collector was subscribed to that symbol's
-- liquidation topic AND hearing from the venue. A minute with no liquidations means "none
-- happened" ONLY inside a span; outside one it is missing data. Receive-time bounds, so edges are
-- fuzzy by Bybit's ~500ms push cadence. Stitch = union of spans across collectors.
CREATE TABLE IF NOT EXISTS liquidation_coverage (
    exchange  TEXT   NOT NULL,
    symbol    TEXT   NOT NULL,
    start_ms  BIGINT NOT NULL,
    end_ms    BIGINT NOT NULL,
    PRIMARY KEY (exchange, symbol, start_ms)
);

-- Live-bot control, one row per bot. mode is RUN | DRAIN | HALT. `coinmon stop` / `coinmon bot
-- resume` (and later the dashboard) write it; the bot reads it every cycle before it places
-- anything. HALT survives restarts: a bot with no row starts HALT and stays idle until resumed.
-- deadline_ms is DRAIN's flatten-at-market time; heartbeat_ms is the bot's last good cycle.
CREATE TABLE IF NOT EXISTS bot_control (
    bot          TEXT   PRIMARY KEY,
    mode         TEXT   NOT NULL,
    reason       TEXT   NOT NULL,
    deadline_ms  BIGINT,
    updated_ms   BIGINT NOT NULL,
    heartbeat_ms BIGINT
);

-- One row per live round trip. Entry columns are written when the position appears, exit columns
-- when it is gone; fills and fees are the venue's own. anchor_close is the 1m close the resting
-- bid was pegged from (what the frozen rule assumed; NULL if the fill happened while the bot was
-- down), fill_px what the venue did. leverage is as set on the venue at fill, e.g. 'isolated 5'.
-- exit_reason: tp | time | other (panic, liquidation, manual: see exit_dir, the venue's fill
-- direction). Natural key: oids are unique per venue, so separate machines stitch by upsert.
CREATE TABLE IF NOT EXISTS bot_trades (
    bot          TEXT             NOT NULL,
    venue        TEXT             NOT NULL,
    coin         TEXT             NOT NULL,
    entry_oid    BIGINT           NOT NULL,
    anchor_close DOUBLE PRECISION,
    sz           DOUBLE PRECISION NOT NULL,
    fill_px      DOUBLE PRECISION NOT NULL,
    fill_ms      BIGINT           NOT NULL,
    entry_fee    DOUBLE PRECISION NOT NULL,
    leverage     TEXT             NOT NULL,
    liq_px       DOUBLE PRECISION,
    tp_px        DOUBLE PRECISION,
    tp_oid       BIGINT,
    time_oid     BIGINT,
    exit_px      DOUBLE PRECISION,
    exit_ms      BIGINT,
    exit_fee     DOUBLE PRECISION,
    exit_reason  TEXT,
    exit_dir     TEXT,
    PRIMARY KEY (bot, venue, entry_oid)
);
