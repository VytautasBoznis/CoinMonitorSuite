from __future__ import annotations

import argparse
import json
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
from coinmon.data.adapters.binance import BinanceAdapter
from coinmon.data.adapters.bybit import BybitAdapter
from coinmon.data.candles import load_candles
from coinmon.data.discovery import rank_spot, summarize_coverage
from coinmon.feed import BarView, CostModel
from coinmon.live.feed import LiveFeed
from coinmon.live.runner import ForwardRunner
from coinmon.scraper import service
from coinmon.search.evidence import (
    build_evidence,
    certify,
    pool_trades,
    select_eval_pairs,
)
from coinmon.search.ga import GAConfig
from coinmon.search.genome import Genome, validate
from coinmon.search.nullmodel import NullResult, random_genome_null
from coinmon.search.runner import (
    CandleCache,
    FitnessParams,
    discover_universe,
    run_search,
    summarize_sweep,
    sweep_row,
)
from coinmon.search.stability import run_stability
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


# Backtest-history + trade venues (chunk T). Binance is history-only ([[train-usdt-certify-usdc]]).
_ADAPTERS = {"bybit": BybitAdapter, "binance": BinanceAdapter}


def _markets(args: argparse.Namespace) -> None:
    # Chunk T: discover candidate spot bases to scrape, ranked by liquidity. Prints a JSON array
    # ready to paste into COINMON_SYMBOLS. Read-only public data; no keys, no orders.
    import ccxt

    exchange = getattr(ccxt, args.exchange)({"enableRateLimit": True})
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    ranked = rank_spot(markets, tickers, args.quote, limit=args.limit)

    print(f"top {len(ranked)} active {args.quote} spot pairs on {args.exchange} by 24h volume:\n")
    for sym, vol in ranked:
        print(f"  {sym:<16} 24h quote vol {vol:,.0f}")
    print("\nCOINMON_SYMBOLS=" + json.dumps([sym for sym, _ in ranked]))


def _coverage(args: argparse.Namespace) -> None:
    # Chunk T: post-scrape report — how many bars and what date span each stored series has, and
    # the resulting auto-built search universe per quote. Tells the alpha hunt its usable universe.
    conn = db.connect()
    try:
        stats = db.series_stats(conn)
    finally:
        conn.close()
    print(summarize_coverage(stats, min_bars=args.min_bars))


def _backfill(args: argparse.Namespace) -> None:
    # Chunk T: one-shot history backfill for a venue (e.g. Binance USDT 2017+ for training data).
    # Reuses the scraper's ingest path; no polling loop. Read-only public data; no keys, no orders.
    if args.since:
        service.settings.backfill_start = args.since  # ingest_series reads settings.backfill_start
    adapter = _ADAPTERS[args.exchange]()
    # Multi-year exchange history has genuine downtime gaps (e.g. Binance early 2018). --allow-gaps
    # stores the REAL bars across them (never fabricated) instead of rejecting the page.
    adapter.require_contiguous = not args.allow_gaps
    conn = db.connect()
    try:
        db.init_schema(conn)
        total = 0
        for symbol in args.symbols:
            for timeframe in args.timeframes:
                try:
                    n = service.ingest_series(adapter, conn, symbol, timeframe)
                    print(f"  {args.exchange} {symbol} {timeframe}: {n} candles")
                    total += n
                except Exception as exc:  # one bad series must not abort the whole backfill
                    print(f"  {args.exchange} {symbol} {timeframe}: SKIPPED ({exc})")
    finally:
        conn.close()
    print(f"backfilled {total} candles from {args.exchange}")


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
        # Chunk N4: the universe is auto-built from the coins the scraper has stored (every USDC leg
        # + every coin/coin ratio), not a hand-curated list — so the search scales with the DB.
        universe = discover_universe(
            db.list_series(conn),
            exchange=settings.exchange,
            quote=settings.quote_currency,
            timeframe=args.timeframe,
        )
        print(f"universe: {len(universe)} pairs auto-built from stored {args.timeframe} candles\n")
        # The connection stays open for the whole run: CandleCache reads each pair lazily.
        report = run_search(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe),
            settings.taker_fee,
            GAConfig(
                population=args.population,
                generations=args.generations,
                seed=args.seed,
                universe=universe,
            ),
            fitness_params=FitnessParams(
                folds=args.folds, embargo_bars=args.embargo, min_trades=args.min_trades
            ),
            fragility_runs=args.stress,
            holdout_fraction=args.holdout,
            graduate_min_trades=args.graduate_min_trades,
            cross_pair_n=args.cross_pair,
            cross_pair_min=args.cross_pair_min,
            workers=args.workers,
        )
    finally:
        conn.close()

    print(
        f"GA search over {args.timeframe} candles "
        f"(pop={args.population}, gens={args.generations}, seed={args.seed})\n"
    )
    print(report.summary())


def _sweep(args: argparse.Namespace) -> None:
    # Chunk N6: run the SAME graduation search across a range of seeds and aggregate the verdicts —
    # the payoff test for whether GOs name a consistent edge or hop pairs by seed. Shares one DB
    # connection + CandleCache across seeds, so the candles are read once, not once per seed.
    if args.holdout <= 0:
        raise SystemExit("sweep needs --holdout > 0: the gate is what produces a verdict")
    conn = db.connect()
    try:
        universe = discover_universe(
            db.list_series(conn),
            exchange=settings.exchange,
            quote=settings.quote_currency,
            timeframe=args.timeframe,
        )
        print(f"universe: {len(universe)} pairs auto-built from stored {args.timeframe} candles\n")
        cache = CandleCache(lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe))
        rows = []
        for seed in range(args.start_seed, args.start_seed + args.seeds):
            report = run_search(
                lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe),
                settings.taker_fee,
                GAConfig(
                    population=args.population,
                    generations=args.generations,
                    seed=seed,
                    universe=universe,
                ),
                fitness_params=FitnessParams(
                    folds=args.folds, embargo_bars=args.embargo, min_trades=args.min_trades
                ),
                fragility_runs=args.stress,
                holdout_fraction=args.holdout,
                graduate_min_trades=args.graduate_min_trades,
                cross_pair_n=args.cross_pair,
                cross_pair_min=args.cross_pair_min,
                workers=args.workers,
                cache=cache,
            )
            print(report.graduation.summary())
            print()
            rows.append(sweep_row(seed, report))
    finally:
        conn.close()

    print(summarize_sweep(rows))


def _stability(args: argparse.Namespace) -> None:
    # Walk-forward parameter stability: re-run the full graduation search on each rolling window and
    # measure whether the winners recur (selection agreement) and whether a window's winner still
    # graduates on the next window's later, unseen bars (forward persistence). The honest read on
    # whether 'passed the gate' is a stable edge or a holdout-luck artifact (nested-holdout lesson).
    if args.holdout <= 0:
        raise SystemExit("stability needs --holdout > 0: each window graduates on its own tail")
    conn = db.connect()
    try:
        universe = discover_universe(
            db.list_series(conn),
            exchange=settings.exchange,
            quote=settings.quote_currency,
            timeframe=args.timeframe,
        )
        print(f"universe: {len(universe)} pairs auto-built from stored {args.timeframe} candles\n")
        report = run_stability(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe),
            settings.taker_fee,
            GAConfig(
                population=args.population,
                generations=args.generations,
                seed=args.seed,
                universe=universe,
            ),
            holdout_fraction=args.holdout,
            window_size=args.window,
            step=args.step,
            n_windows=args.windows,
            fitness_params=FitnessParams(
                folds=args.folds, embargo_bars=args.embargo, min_trades=args.min_trades
            ),
            fragility_runs=args.stress,
            graduate_min_trades=args.graduate_min_trades,
            workers=args.workers,
        )
    finally:
        conn.close()

    print(
        f"walk-forward stability over {args.timeframe} candles "
        f"(window={args.window}, step={args.step}, seed={args.seed})\n"
    )
    print(report.summary())


def _genome_from_args(args: argparse.Namespace) -> Genome:
    """Build + validate the frozen genome the certify/nullcheck commands take on the CLI."""
    genome = Genome(
        family=args.family,
        pair=args.pair,
        params=json.loads(args.params),
        direction=args.direction,
        leverage=args.leverage,
        trend_period=args.trend_period,
        stop_pct=args.stop,
    )
    validate(genome)
    return genome


def _genome_spec(genome: Genome) -> dict:
    """A JSON-serializable view of a genome — so a null file records exactly which genome it
    calibrates, and certify can refuse a null built for a different one."""
    return {
        "family": genome.family,
        "pair": genome.pair,
        "params": dict(genome.params),
        "direction": genome.direction,
        "leverage": genome.leverage,
        "trend_period": genome.trend_period,
        "stop_pct": genome.stop_pct,
    }


def _load_null(path: str, genome: Genome, timeframe: str) -> bool:
    """Load a nullcheck JSON and return its ``beaten`` verdict for C4 — but only after confirming
    it was built for THIS genome + timeframe, so the wrong null can't be applied by accident."""
    with open(path) as fh:
        data = json.load(fh)
    if data.get("genome") != _genome_spec(genome) or data.get("timeframe") != timeframe:
        raise SystemExit(
            f"null file {path} was built for a different genome/timeframe — re-run nullcheck"
        )
    return NullResult.from_dict(data["null"]).beaten


def _certify(args: argparse.Namespace) -> None:
    # Chunk U: pool a FROZEN genome's per-trade OOS ledger across decorrelated pairs x rolling
    # window holdouts and judge it against the Edge Certificate (N>=300, Wilson bound > 0.50,
    # expectancy CI > 0, regime spread). The genome is given on the CLI (no winner-file persistence
    # yet). C4's null verdict comes from a nullcheck JSON via --null (chunk V); C6 fragility stays
    # PENDING until the sweep supplies it.
    genome = _genome_from_args(args)
    null_beaten = _load_null(args.null, genome, args.timeframe) if args.null else None
    conn = db.connect()
    try:
        def read(symbol: str) -> pd.DataFrame:
            return db.read_candles(conn, settings.exchange, symbol, args.timeframe)

        universe = discover_universe(
            db.list_series(conn),
            exchange=settings.exchange,
            quote=settings.quote_currency,
            timeframe=args.timeframe,
        )
        eval_pairs = select_eval_pairs(
            genome, read, universe, args.eval_pairs,
            holdout_fraction=args.holdout, seed=args.seed,
        )
        print(f"pooling {genome.family} on {len(eval_pairs)} pairs: {', '.join(eval_pairs)}\n")
        pooled = pool_trades(
            genome, read, settings.taker_fee, eval_pairs,
            window_size=args.window, step=args.step, holdout_fraction=args.holdout,
        )
    finally:
        conn.close()

    evidence = build_evidence(pooled, seed=args.seed, n_regimes=args.regimes)
    certificate = certify(evidence, null_beaten=null_beaten)
    print(certificate.summary())


def _nullcheck(args: argparse.Namespace) -> None:
    # Chunk V1: the random-genome null (C4 of the Edge Certificate). Score the candidate genome by
    # its pooled-ledger t_exp, then sample N random genomes scored the SAME way over the SAME eval
    # grid and ask whether the candidate clears the best-of-M null. Writes the result to JSON that
    # `certify --null` consumes. A data-mined artifact fails to beat the luckiest random try here.
    genome = _genome_from_args(args)
    conn = db.connect()
    try:
        def read(symbol: str) -> pd.DataFrame:
            return db.read_candles(conn, settings.exchange, symbol, args.timeframe)

        universe = discover_universe(
            db.list_series(conn),
            exchange=settings.exchange,
            quote=settings.quote_currency,
            timeframe=args.timeframe,
        )
        eval_pairs = select_eval_pairs(
            genome, read, universe, args.eval_pairs,
            holdout_fraction=args.holdout, seed=args.seed,
        )
        print(
            f"pooling candidate {genome.family} on {len(eval_pairs)} pairs, then {args.n_genomes} "
            f"random genomes over the same grid...\n"
        )
        candidate = build_evidence(
            pool_trades(
                genome, read, settings.taker_fee, eval_pairs,
                window_size=args.window, step=args.step, holdout_fraction=args.holdout,
            ),
            seed=args.seed, resamples=args.evidence_resamples, n_regimes=args.regimes,
        )
        result = random_genome_null(
            candidate.t_exp,
            read,
            settings.taker_fee,
            eval_pairs,
            universe=universe,
            n_genomes=args.n_genomes,
            sample_seed=args.seed,
            boot_seed=args.seed,
            evidence_resamples=args.evidence_resamples,
            n_regimes=args.regimes,
            window_size=args.window,
            step=args.step,
            holdout_fraction=args.holdout,
        )
    finally:
        conn.close()

    print(result.summary())
    with open(args.out, "w") as fh:
        json.dump(
            {"genome": _genome_spec(genome), "timeframe": args.timeframe, "null": result.to_dict()},
            fh,
            indent=2,
        )
    print(f"\nwrote {args.out} — feed it to `certify --null {args.out}` for C4")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coinmon", description="CoinMonitorSuite backtester")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch-data", help="Retired — ingestion is the scraper service")
    p_fetch.add_argument("--symbol", required=True, help="e.g. BTC/USDC")
    p_fetch.add_argument("--timeframe", default="1h")
    p_fetch.add_argument("--days", type=int, default=90)
    p_fetch.set_defaults(func=_fetch_data)

    p_markets = sub.add_parser(
        "markets",
        help="Discover candidate spot bases to scrape, ranked by 24h volume (chunk T)",
    )
    p_markets.add_argument(
        "--exchange", default="bybit", choices=sorted(_ADAPTERS), help="venue to query"
    )
    p_markets.add_argument(
        "--quote",
        default="USDT",
        help="quote currency to rank (USDT for training history, USDC for the trade venue)",
    )
    p_markets.add_argument(
        "--limit", type=int, default=30, metavar="N", help="how many top pairs to list"
    )
    p_markets.set_defaults(func=_markets)

    p_backfill = sub.add_parser(
        "backfill",
        help="One-shot history backfill for a venue (e.g. Binance USDT 2017+ training data)",
    )
    p_backfill.add_argument(
        "--exchange", default="binance", choices=sorted(_ADAPTERS), help="venue to backfill from"
    )
    p_backfill.add_argument(
        "--symbols", nargs="+", required=True, metavar="SYM", help="e.g. BTC/USDT ETH/USDT"
    )
    p_backfill.add_argument(
        "--timeframes", nargs="+", default=["1d"], metavar="TF", help="e.g. 1d 4h"
    )
    p_backfill.add_argument(
        "--since",
        default="",
        metavar="ISO_DATE",
        help="earliest bar to fetch (e.g. 2017-01-01); default uses the configured backfill start",
    )
    p_backfill.add_argument(
        "--allow-gaps",
        action="store_true",
        help="store real bars across genuine exchange-downtime gaps instead of rejecting them "
        "(never fabricates bars; for multi-year history like Binance 2017+)",
    )
    p_backfill.set_defaults(func=_backfill)

    p_cov = sub.add_parser(
        "coverage",
        help="Report bars-per-series + date spans + usable universe size for stored candles",
    )
    p_cov.add_argument(
        "--min-bars",
        type=int,
        default=800,
        metavar="N",
        help="bar count a series must clear to count toward the usable universe (default 800)",
    )
    p_cov.set_defaults(func=_coverage)

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
        default=15,
        metavar="N",
        help="minimum holdout trades for the graduation gate to pass (with --holdout)",
    )
    p_search.add_argument(
        "--cross-pair",
        type=int,
        default=0,
        metavar="N",
        help="chunk O: after a GO, re-graduate the SAME genome on N decorrelated peer pairs and "
        "tag it golden/specialist (0 = skip). Needs --holdout. A trust label, never a kill gate.",
    )
    p_search.add_argument(
        "--cross-pair-min",
        type=int,
        default=3,
        metavar="K",
        help="minimum cross-pair passes (of --cross-pair N) to earn the 'golden' tier (default 3)",
    )
    p_search.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="CPU processes for the per-genome fitness map (0 = all cores; 1 = serial, default). "
        "Identical results to serial — only the pure genome scoring is parallelized.",
    )
    p_search.set_defaults(func=_search)

    p_sweep = sub.add_parser(
        "sweep",
        help="Run the graduation search across many seeds and aggregate GO/NO-GO (chunk N6)",
    )
    p_sweep.add_argument("--timeframe", default="1d")
    p_sweep.add_argument("--population", type=int, default=30, metavar="N")
    p_sweep.add_argument("--generations", type=int, default=12, metavar="N")
    p_sweep.add_argument(
        "--seeds", type=int, default=10, metavar="N", help="number of seeds to run"
    )
    p_sweep.add_argument(
        "--start-seed", type=int, default=0, metavar="S", help="first seed (runs S..S+seeds-1)"
    )
    p_sweep.add_argument("--folds", type=int, default=4, metavar="N", help="OOS scoring folds")
    p_sweep.add_argument(
        "--embargo", type=int, default=5, metavar="BARS", help="purge between folds"
    )
    p_sweep.add_argument(
        "--min-trades",
        type=int,
        default=20,
        metavar="N",
        help="trade-count floor below which a genome is penalized",
    )
    p_sweep.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="fragility kill-filter runs per winner (0 = default 200 under the holdout gate)",
    )
    p_sweep.add_argument(
        "--holdout",
        type=float,
        default=0.2,
        metavar="FRACTION",
        help="never-searched holdout fraction the graduation gate runs on (default 0.2)",
    )
    p_sweep.add_argument(
        "--graduate-min-trades",
        type=int,
        default=15,
        metavar="N",
        help="minimum holdout trades for a seed's winner to graduate GO",
    )
    p_sweep.add_argument(
        "--cross-pair",
        type=int,
        default=0,
        metavar="N",
        help="chunk O: tag each seed's GO golden/specialist by re-graduating it on N decorrelated "
        "peer pairs; the sweep then counts golden vs specialist across seeds (0 = skip)",
    )
    p_sweep.add_argument(
        "--cross-pair-min",
        type=int,
        default=3,
        metavar="K",
        help="minimum cross-pair passes (of --cross-pair N) to earn the 'golden' tier (default 3)",
    )
    p_sweep.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="CPU processes for the per-genome fitness map (0 = all cores; 1 = serial, default)",
    )
    p_sweep.set_defaults(func=_sweep)

    p_stab = sub.add_parser(
        "stability",
        help="Walk-forward parameter stability: re-run the search per rolling window, measure "
        "selection agreement + forward persistence (does a GO survive the next regime?)",
    )
    p_stab.add_argument("--timeframe", default="1d")
    p_stab.add_argument("--population", type=int, default=30, metavar="N")
    p_stab.add_argument("--generations", type=int, default=12, metavar="N")
    p_stab.add_argument("--seed", type=int, default=0)
    p_stab.add_argument(
        "--window",
        type=float,
        default=0.6,
        metavar="FRAC",
        help="window width as a fraction of each series (default 0.6)",
    )
    p_stab.add_argument(
        "--step",
        type=float,
        default=0.2,
        metavar="FRAC",
        help="how far each window advances, fraction of the series (<= --window, default 0.2)",
    )
    p_stab.add_argument(
        "--windows",
        type=int,
        default=None,
        metavar="N",
        help="cap the number of windows (default: as many as fit in [0, 1])",
    )
    p_stab.add_argument("--folds", type=int, default=4, metavar="N", help="OOS scoring folds")
    p_stab.add_argument(
        "--embargo", type=int, default=5, metavar="BARS", help="purge between folds"
    )
    p_stab.add_argument(
        "--min-trades",
        type=int,
        default=20,
        metavar="N",
        help="trade-count floor below which a genome is penalized",
    )
    p_stab.add_argument(
        "--stress",
        type=int,
        default=0,
        metavar="N",
        help="fragility kill-filter runs per winner (0 = default 200 under the holdout gate)",
    )
    p_stab.add_argument(
        "--holdout",
        type=float,
        default=0.2,
        metavar="FRACTION",
        help="each window's never-searched holdout fraction the graduation gate runs on (def 0.2)",
    )
    p_stab.add_argument(
        "--graduate-min-trades",
        type=int,
        default=15,
        metavar="N",
        help="minimum holdout trades for a window's winner to graduate GO",
    )
    p_stab.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="CPU processes for the per-genome fitness map (0 = all cores; 1 = serial, default)",
    )
    p_stab.set_defaults(func=_stability)

    p_cert = sub.add_parser(
        "certify",
        help="Pool a frozen genome's per-trade OOS ledger across pairs x windows and judge it "
        "against the Edge Certificate (N>=300, Wilson bound, expectancy CI, regimes) (chunk U)",
    )
    p_cert.add_argument("--timeframe", default="1d")
    p_cert.add_argument("--family", required=True, help="strategy family, e.g. rsi_meanreversion")
    p_cert.add_argument("--pair", required=True, help="the genome's own pair, e.g. BNB/ETH")
    p_cert.add_argument(
        "--params", required=True, metavar="JSON", help='family params as JSON, e.g. \'{"period":2,'
        '"oversold":10,"exit_level":60}\''
    )
    p_cert.add_argument("--direction", default="long", choices=("long", "adaptive"))
    p_cert.add_argument("--leverage", type=float, default=1.0, metavar="X")
    p_cert.add_argument("--trend-period", type=float, default=50.0, metavar="BARS")
    p_cert.add_argument(
        "--stop", type=float, default=None, metavar="PCT", help="intrabar stop fraction (def none)"
    )
    p_cert.add_argument("--seed", type=int, default=0, help="seeds the eval-pair pick + bootstrap")
    p_cert.add_argument(
        "--eval-pairs", type=int, default=8, metavar="N",
        help="decorrelated peer pairs to pool alongside the genome's own pair (default 8)",
    )
    p_cert.add_argument(
        "--holdout", type=float, default=0.2, metavar="FRACTION",
        help="each window's OOS holdout tail fraction the ledger is pooled from (default 0.2)",
    )
    p_cert.add_argument("--window", type=float, default=0.6, metavar="FRACTION")
    p_cert.add_argument("--step", type=float, default=0.2, metavar="FRACTION")
    p_cert.add_argument(
        "--regimes", type=int, default=2, metavar="N",
        help="disjoint time regimes to split the pool into for C5 (default 2)",
    )
    p_cert.add_argument(
        "--null", default=None, metavar="FILE",
        help="a nullcheck JSON (chunk V) whose verdict supplies C4 (must match this genome); "
        "without it C4 stays PENDING and the certificate can't reach CERTIFIED",
    )
    p_cert.set_defaults(func=_certify)

    p_null = sub.add_parser(
        "nullcheck",
        help="Chunk V1: score a frozen genome vs a best-of-M random-genome null over the same "
        "pooled OOS grid; writes a JSON verdict `certify --null` consumes as C4",
    )
    p_null.add_argument("--timeframe", default="1d")
    p_null.add_argument("--family", required=True, help="strategy family, e.g. rsi_meanreversion")
    p_null.add_argument("--pair", required=True, help="the genome's own pair, e.g. BNB/ETH")
    p_null.add_argument(
        "--params", required=True, metavar="JSON", help='family params as JSON, e.g. \'{"period":2,'
        '"oversold":10,"exit_level":60}\''
    )
    p_null.add_argument("--direction", default="long", choices=("long", "adaptive"))
    p_null.add_argument("--leverage", type=float, default=1.0, metavar="X")
    p_null.add_argument("--trend-period", type=float, default=50.0, metavar="BARS")
    p_null.add_argument(
        "--stop", type=float, default=None, metavar="PCT", help="intrabar stop fraction (def none)"
    )
    p_null.add_argument("--seed", type=int, default=0, help="seeds eval-pair pick, sampling + boot")
    p_null.add_argument(
        "--eval-pairs", type=int, default=8, metavar="N",
        help="decorrelated peer pairs to pool alongside the genome's own pair (default 8)",
    )
    p_null.add_argument(
        "--holdout", type=float, default=0.2, metavar="FRACTION",
        help="each window's OOS holdout tail fraction the ledger is pooled from (default 0.2)",
    )
    p_null.add_argument("--window", type=float, default=0.6, metavar="FRACTION")
    p_null.add_argument("--step", type=float, default=0.2, metavar="FRACTION")
    p_null.add_argument(
        "--regimes", type=int, default=2, metavar="N",
        help="disjoint time regimes for the candidate's evidence (kept equal to certify's, def 2)",
    )
    p_null.add_argument(
        "--n-genomes", type=int, default=50, metavar="N",
        help="random genomes to sample for the null (each pooled over the same grid; default 50)",
    )
    p_null.add_argument(
        "--evidence-resamples", type=int, default=2000, metavar="N",
        help="bootstrap resamples for each genome's t_exp; candidate + nulls alike (default 2000)",
    )
    p_null.add_argument(
        "--out", default="null.json", metavar="FILE", help="where to write the verdict JSON",
    )
    p_null.set_defaults(func=_nullcheck)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
