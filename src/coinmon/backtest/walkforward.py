from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion

# The RSI parameter grid the search picks from on each train window. Deliberately COARSE:
# this is a generalization probe, not a fine optimizer. A dense grid just buys more
# in-sample overfit that the out-of-sample test then has to expose. Every combo here keeps
# oversold < exit_level, so the no-trade band is always well-formed.
RSI_GRID: dict[str, list[float]] = {
    "period": [7, 14, 21],
    "oversold": [20.0, 25.0, 30.0, 35.0],
    "exit_level": [45.0, 50.0, 55.0, 60.0],
}


@dataclass(frozen=True)
class Fold:
    """One train→test step: params chosen on the train window, scored out-of-sample on the
    immediately-following test window it never saw."""

    train_start: int  # open_time (ms) of the first train bar
    test_start: int  # open_time (ms) of the first test bar
    test_end: int  # open_time (ms) of the last test bar
    params: tuple[float, ...]  # (period, oversold, exit_level), in RSI_GRID key order
    train_return: float
    oos_return: float
    bh_return: float
    test_trades: int


@dataclass
class WalkForwardResult:
    folds: list[Fold]
    oos_return: float  # strategy return compounded across the stitched OOS test segments
    bh_return: float  # buy & hold over the same stitched OOS span (gross of entry fee)
    overfit_ceiling: float  # best single param set fit on the WHOLE series (in-sample peek)
    default_full_return: float  # default RSI params over the whole series (the prior baseline)

    def summary(self) -> str:
        keys = list(RSI_GRID)
        lines = ["  fold  test window            params(per/os/ex)   train     oos       b&h"]
        for i, f in enumerate(self.folds, 1):
            t0 = pd.to_datetime(f.test_start, unit="ms").date()
            t1 = pd.to_datetime(f.test_end, unit="ms").date()
            p = "/".join(f"{v:g}" for v in f.params)
            lines.append(
                f"  {i:<4}  {t0}→{t1}  {p:<18}  "
                f"{f.train_return:+7.2%}  {f.oos_return:+7.2%}  {f.bh_return:+7.2%}"
            )

        n = len(self.folds)
        positive = sum(1 for f in self.folds if f.oos_return > 0)
        beat = sum(1 for f in self.folds if f.oos_return > f.bh_return)
        distinct = len({f.params for f in self.folds})
        params_pretty = ", ".join(keys) + " (grid order)"

        lines += [
            "",
            f"  OOS stitched return    {self.oos_return:+.2%}  ({n} folds, fresh fit each)",
            f"  buy & hold (same span) {self.bh_return:+.2%}",
            f"  folds OOS-positive     {positive}/{n}",
            f"  folds beat buy & hold  {beat}/{n}",
            f"  param stability        {distinct}/{n} distinct choices  [{params_pretty}]",
            "",
            f"  in-sample ceiling      {self.overfit_ceiling:+.2%}  (best grid fit on the "
            "WHOLE series — overfit upper bound)",
            f"  default params (full)  {self.default_full_return:+.2%}  (prior 14/30/50 baseline)",
        ]
        return "\n".join(lines)


def _run(candles: pd.DataFrame, params: dict[str, float], cash: float, fee: float):
    strategy = RSIMeanReversion(
        period=int(params["period"]),
        oversold=params["oversold"],
        exit_level=params["exit_level"],
    )
    return BacktestEngine(strategy, SpotPortfolio(cash=cash, taker_fee=fee)).run(candles)


def _grid() -> list[dict[str, float]]:
    keys = list(RSI_GRID)
    return [dict(zip(keys, combo)) for combo in product(*RSI_GRID.values())]


def _best_params(candles: pd.DataFrame, cash: float, fee: float, objective: str) -> dict[str, float]:
    """Pick the grid point with the highest ``objective`` metric on ``candles``. NaN scores
    (e.g. a param set that never trades → no profit_factor) lose to any real number."""
    best_params: dict[str, float] = {}
    best_score = float("-inf")
    for params in _grid():
        score = _run(candles, params, cash, fee).metrics[objective]
        if score == score and score > best_score:  # score == score rejects NaN
            best_score = score
            best_params = params
    return best_params


def walk_forward(
    candles: pd.DataFrame,
    taker_fee: float,
    *,
    train_bars: int = 365,
    test_bars: int = 180,
    initial_capital: float = 10_000.0,
    objective: str = "total_return",
) -> WalkForwardResult:
    """Rolling walk-forward: on each fold, fit the RSI grid on a ``train_bars`` window and
    score the chosen params on the next, unseen ``test_bars`` window. The test segments are
    contiguous and back-to-back, so compounding their returns is one continuous out-of-sample
    equity curve, re-fit at every boundary — the honest read on whether the search generalizes.
    """
    n = len(candles)
    if n < train_bars + test_bars:
        raise ValueError(
            f"need at least train+test = {train_bars + test_bars} bars, got {n}"
        )

    folds: list[Fold] = []
    oos_factor = 1.0
    bh_factor = 1.0
    for s in range(train_bars, n - test_bars + 1, test_bars):
        train = candles.iloc[s - train_bars : s].reset_index(drop=True)
        test = candles.iloc[s : s + test_bars].reset_index(drop=True)

        params = _best_params(train, initial_capital, taker_fee, objective)
        train_ret = _run(train, params, initial_capital, taker_fee).metrics["total_return"]
        test_res = _run(test, params, initial_capital, taker_fee)
        oos_ret = test_res.metrics["total_return"]
        # B&H over the test span, gross of the entry fee (a slightly conservative reference:
        # it flatters B&H by ~one taker fee, raising the bar our strategy must clear).
        bh_ret = float(test["close"].iloc[-1] / test["open"].iloc[0] - 1.0)

        oos_factor *= 1.0 + oos_ret
        bh_factor *= 1.0 + bh_ret
        folds.append(
            Fold(
                train_start=int(train["open_time"].iloc[0]),
                test_start=int(test["open_time"].iloc[0]),
                test_end=int(test["open_time"].iloc[-1]),
                params=tuple(params[k] for k in RSI_GRID),
                train_return=train_ret,
                oos_return=oos_ret,
                bh_return=bh_ret,
                test_trades=int(test_res.metrics["trades"]),
            )
        )

    overfit = _best_params(candles, initial_capital, taker_fee, objective)
    overfit_ceiling = _run(candles, overfit, initial_capital, taker_fee).metrics["total_return"]
    default_full = (
        BacktestEngine(RSIMeanReversion(), SpotPortfolio(initial_capital, taker_fee))
        .run(candles)
        .metrics["total_return"]
    )

    return WalkForwardResult(
        folds=folds,
        oos_return=oos_factor - 1.0,
        bh_return=bh_factor - 1.0,
        overfit_ceiling=overfit_ceiling,
        default_full_return=default_full,
    )
