"""Streamlit candle viewer — eyeball the scraped history in TimescaleDB.

Run it from the repo root:

    streamlit run src/coinmon/viewer/app.py

Reads the same DSN as everything else (``COINMON_DB_DSN``). NOTE for local dev: the
docker-compose TimescaleDB is published on host port 5433 (5432 is taken by a native
Postgres), so override the DSN when running on the host:

    COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
        streamlit run src/coinmon/viewer/app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coinmon.data import db


@st.cache_resource
def _conn():
    """One shared connection for the session (cached across reruns)."""
    return db.connect()


def main() -> None:
    st.set_page_config(page_title="CoinMonitor candles", layout="wide")
    st.title("Historic candles")

    conn = _conn()
    series = db.list_series(conn)
    if not series:
        st.warning("No candles in the database yet — is the scraper running?")
        return

    symbols = sorted({s[1] for s in series})
    symbol = st.sidebar.selectbox("Symbol", symbols)
    timeframes = sorted({s[2] for s in series if s[1] == symbol})
    timeframe = st.sidebar.selectbox("Timeframe", timeframes)
    exchange = next(s[0] for s in series if s[1] == symbol and s[2] == timeframe)

    df = db.read_candles(conn, exchange, symbol, timeframe)
    if df.empty:
        st.warning(f"No data for {symbol} {timeframe}.")
        return

    ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    fig = go.Figure(
        go.Candlestick(
            x=ts,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
        )
    )
    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=650,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    first, last = ts.iloc[0], ts.iloc[-1]
    st.caption(f"{exchange} · {symbol} · {timeframe} — {len(df)} bars, {first:%Y-%m-%d} → {last:%Y-%m-%d}")


if __name__ == "__main__":
    main()
