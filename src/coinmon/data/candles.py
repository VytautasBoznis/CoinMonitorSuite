from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from coinmon.config import settings
from coinmon.data.ratio import build_ratio


def load_candles(read: Callable[[str], pd.DataFrame], symbol: str) -> pd.DataFrame:
    """Resolve ``symbol`` to a candle frame via ``read`` (a ``symbol -> frame`` loader). A
    USDC-quoted pair loads directly; any other pair (e.g. ETH/BTC) is synthesized from its
    two USDC legs via ``build_ratio``. Extracted from the CLI so the search loop (chunk C)
    resolves the genome's pair gene through the exact same path the backtest CLI uses."""
    base, quote = symbol.split("/")
    if quote == settings.quote_currency:
        return read(symbol)
    base_leg = read(f"{base}/{settings.quote_currency}")
    quote_leg = read(f"{quote}/{settings.quote_currency}")
    return build_ratio(base_leg, quote_leg)


def split_holdout(
    candles: pd.DataFrame, holdout_fraction: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into ``(search, holdout)``: the LAST ``holdout_fraction`` of bars is the holdout the
    search must never see (chunk D's graduation span), the rest is the search span. Both are
    index-reset so each stands alone as a clean series for the engine. The holdout is carved off
    *before* evolution so the GA's winner faces genuinely unseen bars."""
    if not 0.0 < holdout_fraction < 1.0:
        raise ValueError(f"holdout_fraction must be in (0, 1), got {holdout_fraction}")
    cut = len(candles) - int(len(candles) * holdout_fraction)
    head = candles.iloc[:cut].reset_index(drop=True)
    tail = candles.iloc[cut:].reset_index(drop=True)
    return head, tail
