from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from coinmon.backtest.xsectional import (
    XSectionalConfig,
    backtest_xsectional,
    default_grid,
    load_universe_closes,
    sweep_xsectional,
)


def _closes(series: dict[str, list[float]]) -> pd.DataFrame:
    n = len(next(iter(series.values())))
    index = pd.Index(range(0, n * 86_400_000, 86_400_000), name="open_time")
    return pd.DataFrame(series, index=index)


def test_needs_at_least_two_instruments() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        backtest_xsectional(_closes({"A": list(range(1, 60))}), XSectionalConfig())


def test_rejects_too_short_history() -> None:
    closes = _closes({"A": [1.0] * 10, "B": [1.0] * 10})
    with pytest.raises(ValueError, match="not enough history"):
        backtest_xsectional(closes, XSectionalConfig(lookback=5, skip=1, rebalance=7))


def test_momentum_selects_the_persistent_winner() -> None:
    # A compounds up every bar, B flat, C decays. The top-slice (1 of 3) must always be A, so the
    # strategy tracks A's compounding and beats the equal-weight benchmark.
    n = 80
    a = [1.0 * 1.01**i for i in range(n)]
    b = [1.0] * n
    c = [1.0 * 0.99**i for i in range(n)]
    result = backtest_xsectional(
        _closes({"A": a, "B": b, "C": c}),
        XSectionalConfig(lookback=10, skip=1, top_frac=0.34, rebalance=5, fee=0.0),
    )
    # top_frac 0.34 of 3 eligible rounds to 1 name held.
    assert result.metrics["total_return"] > result.benchmark_metrics["total_return"]
    # Every held position is A during an up-run, so with zero fees every outcome is positive.
    assert result.positions and all(p > 0 for p in result.positions)
    assert result.metrics["win_rate"] == 1.0


def test_no_lookahead_ranking_uses_only_past() -> None:
    # D is flat then rockets AFTER bar 40. A momentum ranker at a rebalance <= 40 must NOT have
    # picked D (its past return is 0 there); a lookahead bug would pick it early and inflate return.
    n = 70
    flat = [1.0] * n
    rising = [1.0] * 41 + [2.0**k for k in range(1, n - 40)]
    up = [1.0 * 1.005**i for i in range(n)]  # a mild steady winner to occupy the top slice early
    result = backtest_xsectional(
        _closes({"UP": up, "FLAT": flat, "SPIKE": rising}),
        XSectionalConfig(lookback=10, skip=1, top_frac=0.34, rebalance=10, fee=0.0),
    )
    # The first rebalance is at bar 11 (lookback+skip); SPIKE is flat through 41, so early held
    # positions must be UP, not SPIKE. If lookahead leaked, an early position would show SPIKE's
    # 2x jumps and the first outcome would be far above UP's ~5% per 10-bar hold.
    first_outcome = result.positions[0]
    assert first_outcome < 0.10  # UP over 10 bars ~ 1.005**10 - 1 ≈ 5%, nowhere near a SPIKE 2x


def test_fees_drag_returns() -> None:
    a = [1.0 * 1.01**i for i in range(60)]
    b = [1.0 * 1.005**i for i in range(60)]
    cfg_free = XSectionalConfig(lookback=10, skip=1, top_frac=0.5, rebalance=3, fee=0.0)
    cfg_fee = XSectionalConfig(lookback=10, skip=1, top_frac=0.5, rebalance=3, fee=0.002)
    free = backtest_xsectional(_closes({"A": a, "B": b}), cfg_free)
    fee = backtest_xsectional(_closes({"A": a, "B": b}), cfg_fee)
    assert fee.metrics["total_return"] < free.metrics["total_return"]


def test_load_universe_closes_aligns_and_skips_empty() -> None:
    def read(sym: str) -> pd.DataFrame:
        if sym == "EMPTY/USDT":
            return pd.DataFrame(columns=["open_time", "close"])
        offset = 0 if sym == "A/USDT" else 2  # B lists two bars late
        rows = [(i, 1.0 + i) for i in range(offset, 6)]
        return pd.DataFrame(rows, columns=["open_time", "close"])

    frame = load_universe_closes(read, ["A/USDT", "B/USDT", "EMPTY/USDT"])
    assert list(frame.columns) == ["A/USDT", "B/USDT"]  # empty dropped
    assert np.isnan(frame.loc[0, "B/USDT"])  # B not listed at bar 0
    assert frame.loc[5, "B/USDT"] == 6.0


def test_short_leg_profits_on_the_falling_basket() -> None:
    # A rises, C falls. Long-only (no short) holds A and skips C's decline. Adding a short leg on
    # the bottom slice should ALSO harvest C's fall, so the long-short book out-returns long-only.
    n = 80
    a = [1.0 * 1.01**i for i in range(n)]
    b = [1.0] * n
    c = [1.0 * 0.99**i for i in range(n)]
    closes = _closes({"A": a, "B": b, "C": c})
    cfg = dict(lookback=10, skip=1, top_frac=0.34, rebalance=5, fee=0.0)
    long_only = backtest_xsectional(closes, XSectionalConfig(**cfg, short_frac=0.0))
    long_short = backtest_xsectional(closes, XSectionalConfig(**cfg, short_frac=0.34))
    assert long_short.metrics["total_return"] > long_only.metrics["total_return"]
    # The short leg records signed round-trips: shorting C (which falls) is a winning position.
    shorts = [t for t in long_short.trades if t.direction == -1]
    assert shorts and all(t.net_return_pct > 0 for t in shorts)
    assert long_short.metrics["exposure"] == 2.0  # gross = long leg + short leg


def test_trades_ledger_matches_positions() -> None:
    a = [1.0 * 1.01**i for i in range(60)]
    b = [1.0 * 1.005**i for i in range(60)]
    result = backtest_xsectional(
        _closes({"A": a, "B": b}),
        XSectionalConfig(lookback=10, skip=1, top_frac=0.5, short_frac=0.5, rebalance=5, fee=0.001),
    )
    # One TradeRecord per pooled position, same signed net returns, all time-stamped for the cert.
    assert len(result.trades) == len(result.positions)
    assert [t.net_return_pct for t in result.trades] == result.positions
    assert all(t.exit_time > t.entry_time for t in result.trades)


def test_sweep_records_all_configs_ranked_by_edge() -> None:
    a = [1.0 * 1.01**i for i in range(90)]
    b = [1.0] * 90
    c = [1.0 * 0.99**i for i in range(90)]
    closes = _closes({"A": a, "B": b, "C": c})
    configs = [
        XSectionalConfig(lookback=10, skip=1, top_frac=0.34, rebalance=5, fee=0.0),
        XSectionalConfig(lookback=10, skip=1, top_frac=0.34, short_frac=0.34, rebalance=5, fee=0.0),
    ]
    rows = sweep_xsectional(closes, configs)
    assert len(rows) == len(configs)  # every config kept, none hidden
    assert rows[0].edge >= rows[1].edge  # ranked best edge first


def test_default_grid_is_fixed_and_carries_fee() -> None:
    grid = default_grid(fee=0.0007)
    assert len(grid) == 3 * 2 * 3 * 3 * 3  # lookback x skip x top x short x rebalance
    assert all(c.fee == 0.0007 for c in grid)
