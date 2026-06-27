from __future__ import annotations

import argparse
from collections.abc import Callable

import pandas as pd

from coinmon.backtest.engine import BacktestEngine
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.backtest.result import BacktestResult
from coinmon.backtest.stress import run_monte_carlo
from coinmon.backtest.walkforward import walk_forward
from coinmon.config import settings
from coinmon.data import db
from coinmon.data.ratio import build_ratio
from coinmon.feed import BarView, CostModel
from coinmon.strategies.base import Strategy
from coinmon.strategies.ema_crossover import EMACrossover
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion
from coinmon.strategies.stop_loss import StopLoss

# Notional the backtest starts with. Metrics are scale-invariant ratios, so the value only
# affects the readability of absolute equity, not the results.
INITIAL_CAPITAL = 10_000.0

# --strategy name -> zero-arg factory. Cost-aware strategies pull fees from config.
STRATEGIES: dict[str, Callable[[], Strategy]] = {
    "ema_crossover": lambda: EMACrossover(CostModel.from_settings()),
    "rsi_meanreversion": lambda: RSIMeanReversion(),
}


class _BuyAndHold(Strategy):
    """Benchmark: long from the first tradable bar and never sell. Run through the same
    engine so its costs/accounting match the strategy it's compared against."""

    def on_bar(self, view: BarView) -> int:
        return 1


def _fetch_data(args: argparse.Namespace) -> None:
    raise SystemExit(
        "fetch-data is retired: candle ingestion is the scraper service "
        "(coinmon.scraper) writing to TimescaleDB. Run that to populate data."
    )


def _load_candles(read: Callable[[str], pd.DataFrame], symbol: str) -> pd.DataFrame:
    """Resolve ``symbol`` to a candle frame via ``read`` (a ``symbol -> frame`` loader). A
    USDC-quoted pair loads directly; any other pair (e.g. ETH/BTC) is synthesized from its
    two USDC legs via ``build_ratio``."""
    base, quote = symbol.split("/")
    if quote == settings.quote_currency:
        return read(symbol)
    base_leg = read(f"{base}/{settings.quote_currency}")
    quote_leg = read(f"{quote}/{settings.quote_currency}")
    return build_ratio(base_leg, quote_leg)


def _make_portfolio() -> SpotPortfolio:
    return SpotPortfolio(cash=INITIAL_CAPITAL, taker_fee=settings.taker_fee)


def _run(strategy: Strategy, candles: pd.DataFrame) -> BacktestResult:
    return BacktestEngine(strategy, _make_portfolio()).run(candles)


def _backtest(args: argparse.Namespace) -> None:
    conn = db.connect()
    try:
        candles = _load_candles(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe), args.symbol
        )
    finally:
        conn.close()
    if candles.empty:
        raise SystemExit(
            f"no candles stored for {args.symbol} {args.timeframe} — run the scraper first"
        )

    def make_strategy() -> Strategy:
        strategy = STRATEGIES[args.strategy]()
        if args.stop_loss:
            strategy = StopLoss(strategy, args.stop_loss)
        return strategy

    result = _run(make_strategy(), candles)
    benchmark = _run(_BuyAndHold(), candles)

    label = args.strategy + (f" +{args.stop_loss:.0%} stop" if args.stop_loss else "")
    print(f"{label} on {args.symbol} {args.timeframe} ({len(candles)} bars)\n")
    print(result.summary())
    print("\nbuy & hold:")
    print(benchmark.summary())

    if args.stress:
        mc = run_monte_carlo(
            make_strategy,
            _make_portfolio,
            candles,
            runs=args.stress,
            benchmark_return=benchmark.metrics["total_return"],
        )
        print(f"\nfragility stress ({args.stress} runs, slippage+fill-failure):")
        print(mc.summary())


def _walk_forward(args: argparse.Namespace) -> None:
    conn = db.connect()
    try:
        candles = _load_candles(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe), args.symbol
        )
    finally:
        conn.close()
    if candles.empty:
        raise SystemExit(
            f"no candles stored for {args.symbol} {args.timeframe} — run the scraper first"
        )

    result = walk_forward(
        candles,
        settings.taker_fee,
        train_bars=args.train,
        test_bars=args.test,
        embargo_bars=args.embargo,
        initial_capital=INITIAL_CAPITAL,
        objective=args.objective,
    )
    print(
        f"walk-forward RSI on {args.symbol} {args.timeframe} ({len(candles)} bars, "
        f"train={args.train}/test={args.test}/embargo={args.embargo}, select by {args.objective})\n"
    )
    print(result.summary())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coinmon", description="CoinMonitorSuite backtester")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch-data", help="Retired — ingestion is the scraper service")
    p_fetch.add_argument("--symbol", required=True, help="e.g. BTC/USDC")
    p_fetch.add_argument("--timeframe", default="1h")
    p_fetch.add_argument("--days", type=int, default=90)
    p_fetch.set_defaults(func=_fetch_data)

    p_bt = sub.add_parser("backtest", help="Run a strategy over stored candles")
    p_bt.add_argument(
        "--strategy", required=True, choices=sorted(STRATEGIES), help="e.g. ema_crossover"
    )
    p_bt.add_argument("--symbol", required=True, help="e.g. BTC/USDC, or ETH/BTC (synthetic ratio)")
    p_bt.add_argument("--timeframe", default="1h")
    p_bt.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="also run the Phase 1.5 fragility kill-filter over N perturbed runs (off by default)",
    )
    p_bt.add_argument(
        "--stop-loss",
        type=float,
        default=0.0,
        metavar="PCT",
        help="wrap the strategy in a stop-loss exit at PCT drawdown from entry, e.g. 0.05 (off)",
    )
    p_bt.set_defaults(func=_backtest)

    p_wf = sub.add_parser(
        "walk-forward",
        help="Out-of-sample RSI param search: fit a grid per train window, score on the next",
    )
    p_wf.add_argument("--symbol", required=True, help="e.g. ETH/BTC (synthetic ratio)")
    p_wf.add_argument("--timeframe", default="1d")
    p_wf.add_argument("--train", type=int, default=365, metavar="BARS", help="train window size")
    p_wf.add_argument("--test", type=int, default=180, metavar="BARS", help="test window size")
    p_wf.add_argument(
        "--embargo",
        type=int,
        default=0,
        metavar="BARS",
        help="purge: bars dropped between each train window and its test (default 0)",
    )
    p_wf.add_argument(
        "--objective",
        default="total_return",
        choices=["total_return", "calmar", "profit_factor", "sharpe"],
        help="metric the search maximizes on each train window",
    )
    p_wf.set_defaults(func=_walk_forward)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
