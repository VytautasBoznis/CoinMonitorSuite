from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from coinmon.config import settings


def align_funding(funding: pd.DataFrame, candle_times: Sequence[int]) -> np.ndarray:
    """Aggregate 8h funding settlements onto a candle grid (chunk W3 step 2).

    Returns a per-bar array aligned 1:1 with ``candle_times`` (ascending bar open-times, the
    ``db.read_funding`` frame's ``funding_time``/``rate`` columns as input), where element ``i`` is
    the SUM of every settlement whose ``funding_time`` falls in bar ``i``'s window
    ``[candle_times[i], candle_times[i+1])``. This is exactly the per-bar aggregate
    ``BacktestEngine.run(candles, funding=...)`` charges at each bar close — summing the three
    daily 8h settlements to the backtest's bar granularity, the same granularity the bar prices
    support (the close-only convention of the perp book).

    A settlement exactly on a bar's open-time belongs to that bar. Settlements before the first bar
    are dropped; the final bar's window is bounded by one bar-spacing past its open (a uniform
    grid), so settlements beyond the last stored bar — which belong to bars we don't have — are
    dropped too. ``rate`` is summed, not averaged: two +0.01% settlements in one bar cost the
    holder 0.02%."""
    times = np.asarray(candle_times, dtype=np.int64)
    out = np.zeros(len(times))
    if funding.empty or len(times) == 0:
        return out
    ft = funding["funding_time"].to_numpy(dtype=np.int64)
    rate = funding["rate"].to_numpy(dtype=float)
    # Upper bound of the last bar = one bar-spacing past its open (drops far-future settlements).
    last_upper = (
        int(times[-1]) + int(times[-1] - times[-2])
        if len(times) >= 2
        else int(np.iinfo(np.int64).max)
    )
    idx = np.searchsorted(times, ft, side="right") - 1  # bar each settlement falls into
    keep = (idx >= 0) & (ft < last_upper)
    np.add.at(out, idx[keep], rate[keep])
    return out


def attach_funding(
    frame: pd.DataFrame,
    pair: str,
    read_funding: Callable[[str], pd.DataFrame],
) -> pd.DataFrame:
    """Attach a per-bar ``funding_rate`` column to a DIRECT perp pair's candle frame (chunk W3
    step 2c — the seam that finally makes ``funding_carry`` searchable, not just registered).

    Only a direct ``BASE/QUOTE`` leg (``QUOTE == settings.quote_currency``) has a tradable perp and
    thus funding; a synthetic ratio (``BASE/BASE2``) is not a perp and is returned unchanged.
    ``read_funding`` resolves the pair to its funding-settlement frame (``funding_time``/``rate``,
    e.g. ``db.read_funding``); the CALLER maps the pair to its perp symbol (funding is stored under
    ``BASE/QUOTE:QUOTE``). When the perp has no stored funding the frame is returned unchanged — the
    byte-unchanged path (no column, so the engine adds no funding feature or cashflow). Otherwise
    the 8h settlements are aggregated onto the bar grid (``align_funding``) and stored as
    ``funding_rate`` so every downstream slice (fold, holdout, fragility, pooled window) carries it
    for free and the engine charges + exposes it point-in-time."""
    if pair.split("/")[1] != settings.quote_currency:
        return frame
    funding = read_funding(pair)
    if funding.empty:
        return frame
    aligned = align_funding(funding, frame["open_time"].to_numpy())
    return frame.assign(funding_rate=aligned)
