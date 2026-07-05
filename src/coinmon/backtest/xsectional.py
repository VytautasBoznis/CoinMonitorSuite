from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from coinmon.backtest.metrics import summarize

# Cross-sectional (relative) momentum portfolio — the first post-GA candidate
# ([[cross-sectional-momentum-portfolio]], W5). This is a MULTI-instrument backtester, distinct
# from the single-series BarStepper/BacktestEngine: the bet is on the *relative ordering* of many
# coins, not one pair's timing, which is what diversifies away the per-pair overfitting that killed
# the GA sweeps. Every rebalance we rank the whole universe by trailing return, hold the top slice
# equal-weighted, and pay fees on turnover. Testing/certification follows the portfolio-search
# protocol (no pair parameter; benchmark is the equal-weight universe, i.e. crypto beta).


@dataclass(frozen=True, slots=True)
class XSectionalConfig:
    """One momentum-rotation configuration. Defaults are the documented "monthly momentum, weekly
    rebalance, top-quintile" starting point; the full grid over these axes is the next chunk
    ([[portfolio-search-protocol]])."""

    lookback: int = 28  # bars of trailing return the ranking is computed over
    skip: int = 1  # most-recent bars skipped before ranking (short-term reversal guard)
    top_frac: float = 0.2  # long the top fraction of eligible coins, equal-weighted
    rebalance: int = 7  # bars between rebalances (7 = weekly on 1d bars)
    fee: float = 0.001  # taker fee per side, charged on turnover at each rebalance


@dataclass
class XSectionalResult:
    """A rotation run: the strategy equity curve, the equal-weight-universe benchmark it must beat,
    both metric dicts, and the pooled per-position outcome ledger (each held coin's net
    holding-period return — the N the Edge Certificate will pool over)."""

    equity_curve: pd.Series
    benchmark_curve: pd.Series
    metrics: dict[str, float]
    benchmark_metrics: dict[str, float]
    positions: list[float]  # net holding-period return per taken position; success = > 0
    n_rebalances: int

    def summary(self) -> str:
        edge = self.metrics["total_return"] - self.benchmark_metrics["total_return"]
        lines = [
            f"  rebalances             {self.n_rebalances}",
            f"  pooled positions (N)   {len(self.positions)}",
            "",
            "  top-slice momentum:",
        ]
        lines += ["  " + line for line in _summary_block(self.metrics)]
        lines += ["", "  equal-weight universe (benchmark):"]
        lines += ["  " + line for line in _summary_block(self.benchmark_metrics)]
        lines += ["", f"  edge (return vs benchmark)   {edge:+.2%}"]
        return "\n".join(lines)


def _summary_block(metrics: dict[str, float]) -> list[str]:
    order = ["total_return", "max_drawdown", "calmar", "sharpe", "win_rate", "trades"]
    labels = {
        "total_return": "Total return",
        "max_drawdown": "Max drawdown",
        "calmar": "Calmar",
        "sharpe": "Sharpe (per-bar)",
        "win_rate": "Win rate (per-position)",
        "trades": "Positions",
    }
    out = []
    for key in order:
        v = metrics[key]
        if key in ("total_return", "max_drawdown"):
            text = f"{v:+.2%}"
        elif key == "win_rate":
            text = "n/a" if v != v else f"{v:.2%}"  # NaN check
        elif key == "trades":
            text = f"{int(v)}"
        elif v == float("inf"):
            text = "inf"
        else:
            text = f"{v:.2f}"
        out.append(f"  {labels[key]:<24} {text}")
    return out


def _turnover(prev: dict[str, float], new: dict[str, float]) -> float:
    """One-sided turnover: sum of absolute weight changes across the union of held symbols. A full
    swap from N names to N disjoint names is turnover 2.0 (sell 1.0 + buy 1.0)."""
    return sum(abs(new.get(s, 0.0) - prev.get(s, 0.0)) for s in prev.keys() | new.keys())


def _port_return(ret_row: pd.Series, weights: dict[str, float]) -> float:
    """Weighted portfolio return for one bar. A coin with a missing return that bar (gap/delist) is
    held flat (0), never dropped — weights stay summed to 1 so exposure is honest."""
    total = 0.0
    for sym, w in weights.items():
        r = ret_row.get(sym)
        if r == r:  # not NaN
            total += w * r
    return total


def backtest_xsectional(closes: pd.DataFrame, cfg: XSectionalConfig) -> XSectionalResult:
    """Replay a cross-sectional momentum rotation over a wide close-price frame.

    ``closes`` is indexed by ``open_time`` (oldest first), one column per instrument, NaN where a
    coin had no bar yet (listed late). No lookahead: the rank at rebalance bar ``t`` uses only the
    closes
    up to ``t - skip``, positions are entered at ``t``'s close, and returns are earned from ``t``
    forward. The strategy holds the top ``top_frac`` of eligible coins equal-weighted until the next
    rebalance; the benchmark equal-weights the WHOLE eligible universe on the same cadence with the
    same fee model, so the reported edge is momentum-selection net of beta and costs.
    """
    if closes.shape[1] < 2:
        raise ValueError("cross-sectional momentum needs at least 2 instruments")

    times = closes.index
    n = len(times)
    warmup = cfg.lookback + cfg.skip
    if n <= warmup + cfg.rebalance:
        raise ValueError("not enough history for even one rebalance segment")

    ret = closes.pct_change()
    rebalance_bars = list(range(warmup, n - 1, cfg.rebalance))
    seg_ends = rebalance_bars[1:] + [n - 1]

    def eligible(t: int) -> pd.Series:
        """Momentum score per coin with both a full lookback window and a tradeable price now."""
        past = closes.iloc[t - cfg.skip - cfg.lookback]
        recent = closes.iloc[t - cfg.skip]
        mom = recent / past - 1.0
        price_now = closes.iloc[t]
        return mom[mom.notna() & price_now.notna()]

    strat_eq, bench_eq, eq_times = 1.0, 1.0, []
    strat_curve, bench_curve = [], []
    positions: list[float] = []
    prev_w: dict[str, float] = {}
    prev_bw: dict[str, float] = {}

    for start, end in zip(rebalance_bars, seg_ends, strict=True):
        scores = eligible(start)
        if scores.empty:
            continue
        k = max(1, round(len(scores) * cfg.top_frac))
        longs = list(scores.sort_values(ascending=False).index[:k])
        universe = list(scores.index)
        w = {s: 1.0 / len(longs) for s in longs}
        bw = {s: 1.0 / len(universe) for s in universe}

        strat_eq *= 1.0 - cfg.fee * _turnover(prev_w, w)
        bench_eq *= 1.0 - cfg.fee * _turnover(prev_bw, bw)

        for d in range(start + 1, end + 1):
            row = ret.iloc[d]
            strat_eq *= 1.0 + _port_return(row, w)
            bench_eq *= 1.0 + _port_return(row, bw)
            strat_curve.append(strat_eq)
            bench_curve.append(bench_eq)
            eq_times.append(times[d])

        # Pooled per-position ledger: each held coin's net holding-period return (round-trip fee
        # charged once), the per-decision outcome the certificate pools to reach N >= 300.
        entry, exit_ = closes.iloc[start], closes.iloc[end]
        for s in longs:
            hp = exit_[s] / entry[s] - 1.0
            if hp == hp:  # not NaN
                positions.append(hp - 2.0 * cfg.fee)

        prev_w, prev_bw = w, bw

    if not strat_curve:
        raise ValueError("no rebalance produced an eligible universe — check history/lookback")

    index = pd.Index(eq_times, name="open_time")
    equity_curve = pd.Series(strat_curve, index=index, name="equity")
    benchmark_curve = pd.Series(bench_curve, index=index, name="equity")
    return XSectionalResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        metrics=summarize(equity_curve, positions, exposure=1.0),
        benchmark_metrics=summarize(benchmark_curve, [], exposure=1.0),
        positions=positions,
        n_rebalances=len(rebalance_bars),
    )


def load_universe_closes(
    read, symbols: list[str]
) -> pd.DataFrame:
    """Build the wide close-price frame from a ``symbol -> OHLCV frame`` loader. Columns are the
    symbols that returned data, aligned on the union of ``open_time`` (outer join, NaN before a
    coin lists). Kept here so the DB/ccxt calls stay in the CLI, mirroring ``data/discovery.py``."""
    cols: dict[str, pd.Series] = {}
    for sym in symbols:
        frame = read(sym)
        if not frame.empty:
            cols[sym] = frame.set_index("open_time")["close"]
    return pd.DataFrame(cols).sort_index()
