from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from coinmon.backtest.engine import BacktestEngine, StepResult
from coinmon.backtest.portfolio import SpotPortfolio
from coinmon.backtest.result import BacktestResult
from coinmon.backtest.stress import run_monte_carlo
from coinmon.backtest.walkforward import walk_forward
from coinmon.config import settings
from coinmon.data import db
from coinmon.data.candles import load_candles
from coinmon.feed import BarView, CostModel
from coinmon.live.feed import LiveFeed
from coinmon.live.runner import ForwardRunner
from coinmon.search.ga import GAConfig
from coinmon.search.runner import FitnessParams, run_search
from coinmon.strategies.atr_channel import ATRChannelBreakout
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
    "atr_channel": lambda: ATRChannelBreakout(),
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


def _make_portfolio() -> SpotPortfolio:
    return SpotPortfolio(cash=INITIAL_CAPITAL, taker_fee=settings.taker_fee)


def _run(strategy: Strategy, candles: pd.DataFrame) -> BacktestResult:
    return BacktestEngine(strategy, _make_portfolio()).run(candles)


def _backtest(args: argparse.Namespace) -> None:
    conn = db.connect()
    try:
        candles = load_candles(
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
        candles = load_candles(
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


def _fmt_time(open_time: int) -> str:
    return datetime.fromtimestamp(open_time / 1000, UTC).strftime("%Y-%m-%d %H:%M")


def _fmt_rotation(s: StepResult) -> str:
    side = "BUY " if s.position == 1 else "SELL"
    return f"  {_fmt_time(s.open_time)}  {side} @ {s.close:g}"


def _forward(args: argparse.Namespace) -> None:
    conn = db.connect()
    feed = LiveFeed(
        lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe), args.symbol
    )
    runner = ForwardRunner(STRATEGIES[args.strategy](), _make_portfolio())

    # One-shot replay of every bar already stored — same decisions the backtester would make.
    replayed = runner.feed(feed.poll())
    if not replayed:
        conn.close()
        raise SystemExit(
            f"no candles stored for {args.symbol} {args.timeframe} — run the scraper first"
        )

    print(f"forward {args.strategy} on {args.symbol} {args.timeframe} ({len(replayed)} bars)\n")
    rotations = [s for s in replayed if s.filled]
    print(f"replayed {len(replayed)} bars, {len(rotations)} rotations; recent:")
    for s in rotations[-5:]:
        print(_fmt_rotation(s))
    latest = runner.latest
    assert latest is not None  # replayed is non-empty
    held = "LONG" if latest.position == 1 else "FLAT"
    want = "LONG" if latest.target == 1 else "FLAT"
    pending = " -> ROTATE next bar" if latest.target != latest.position else ""
    print(
        f"\nas of {_fmt_time(latest.open_time)}: holding {held}, "
        f"target {want}{pending}; equity {latest.equity:.2f}"
    )

    if not args.follow:
        conn.close()
        return

    print(f"\nfollowing every {args.interval}s (Ctrl-C to stop)...")
    try:
        while True:
            time.sleep(args.interval)
            for s in runner.feed(feed.poll()):
                if s.filled:
                    print(_fmt_rotation(s))
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        conn.close()


def _search(args: argparse.Namespace) -> None:
    conn = db.connect()
    try:
        # The connection stays open for the whole run: CandleCache reads each pair lazily.
        report = run_search(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe),
            settings.taker_fee,
            GAConfig(
                population=args.population,
                generations=args.generations,
                seed=args.seed,
            ),
            fitness_params=FitnessParams(
                folds=args.folds, embargo_bars=args.embargo, min_trades=args.min_trades
            ),
            fragility_runs=args.stress,
            holdout_fraction=args.holdout,
            graduate_min_trades=args.graduate_min_trades,
        )
    finally:
        conn.close()

    print(
        f"GA search over {args.timeframe} candles "
        f"(pop={args.population}, gens={args.generations}, seed={args.seed})\n"
    )
    print(report.summary())


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

    p_fwd = sub.add_parser(
        "forward",
        help="Run a strategy forward over the growing DB (live BarView, same engine as backtest)",
    )
    p_fwd.add_argument(
        "--strategy", required=True, choices=sorted(STRATEGIES), help="e.g. rsi_meanreversion"
    )
    p_fwd.add_argument(
        "--symbol", required=True, help="e.g. BTC/USDC, or ETH/BTC (synthetic ratio)"
    )
    p_fwd.add_argument("--timeframe", default="1d")
    p_fwd.add_argument(
        "--follow",
        action="store_true",
        help="keep polling the DB for new closed bars and print rotations as they happen",
    )
    p_fwd.add_argument(
        "--interval",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="poll interval when --follow is set (default 60)",
    )
    p_fwd.set_defaults(func=_forward)

    p_search = sub.add_parser(
        "search",
        help="Evolutionary search over genomes (family+pair+params), scored OOS + fragility-gated",
    )
    p_search.add_argument("--timeframe", default="1d")
    p_search.add_argument("--population", type=int, default=30, metavar="N")
    p_search.add_argument("--generations", type=int, default=12, metavar="N")
    p_search.add_argument("--seed", type=int, default=0)
    p_search.add_argument("--folds", type=int, default=4, metavar="N", help="OOS scoring folds")
    p_search.add_argument(
        "--embargo", type=int, default=5, metavar="BARS", help="purge between folds"
    )
    p_search.add_argument(
        "--min-trades",
        type=int,
        default=20,
        metavar="N",
        help="trade-count floor below which a genome is penalized",
    )
    p_search.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="fragility kill-filter runs on the winner (0 = skip; defaults to 200 under --holdout)",
    )
    p_search.add_argument(
        "--holdout",
        type=float,
        default=0.0,
        metavar="FRACTION",
        help="carve the last FRACTION of each pair as a never-searched holdout and run the "
        "graduation gate on the winner, e.g. 0.2 (0 = skip, chunk-C behavior)",
    )
    p_search.add_argument(
        "--graduate-min-trades",
        type=int,
        default=5,
        metavar="N",
        help="minimum holdout trades for the graduation gate to pass (with --holdout)",
    )
    p_search.set_defaults(func=_search)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
