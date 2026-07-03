from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
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
from coinmon.data.surrogate import surrogate_legs
from coinmon.feed import BarView, CostModel
from coinmon.live.feed import LiveFeed
from coinmon.live.runner import ForwardRunner
from coinmon.scraper import service
from coinmon.search.ensemble import certify_ensemble
from coinmon.search.evidence import (
    CertifiedRow,
    build_evidence,
    certify,
    pool_segments,
    pool_trades,
    rank_certified,
    select_eval_pairs,
    summarize_certified_sweep,
)
from coinmon.search.ga import GAConfig
from coinmon.search.genome import Genome, decode_portfolio, validate
from coinmon.search.nullmodel import (
    NullResult,
    random_entry_null,
    random_genome_null,
    surrogate_null,
)
from coinmon.search.runner import (
    CandleCache,
    FitnessParams,
    default_embargo,
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


def _funding_reader(conn) -> Callable[[str], pd.DataFrame]:
    """A ``pair -> funding frame`` loader for ``CandleCache`` / evidence pooling (chunk W3 step 2c).
    Funding is stored under the PERP symbol (``BASE/QUOTE:QUOTE``, see ``service.perp_symbol``), so
    this maps the spot pair the search trades to it. ``attach_funding`` only calls it for direct
    perps, so a ratio never hits the DB here."""

    def read_funding(pair: str) -> pd.DataFrame:
        return db.read_funding(conn, settings.exchange, f"{pair}:{pair.split('/')[1]}")

    return read_funding


def _resolve_embargo(args: argparse.Namespace) -> int:
    """Chunk X: an explicit ``--embargo`` wins; otherwise the per-timeframe default keeps the
    ~5-day fold purge constant across timeframes (a 4h search needs 30 bars, not 5)."""
    return args.embargo if args.embargo is not None else default_embargo(args.timeframe)


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
        embargo = _resolve_embargo(args)
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
                folds=args.folds, embargo_bars=embargo, min_trades=args.min_trades
            ),
            fragility_runs=args.stress,
            holdout_fraction=args.holdout,
            graduate_min_trades=args.graduate_min_trades,
            cross_pair_n=args.cross_pair,
            cross_pair_min=args.cross_pair_min,
            workers=args.workers,
            read_funding=_funding_reader(conn),
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
        cache = CandleCache(
            lambda s: db.read_candles(conn, settings.exchange, s, args.timeframe),
            _funding_reader(conn),
        )
        embargo = _resolve_embargo(args)
        rows = []
        go_genomes = []
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
                    folds=args.folds, embargo_bars=embargo, min_trades=args.min_trades
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
            if args.certify and report.graduation.passed:
                go_genomes.append(report.graduation.genome)

        print(summarize_sweep(rows))

        if args.certify:
            _certify_sweep_winners(conn, args, universe, go_genomes)
    finally:
        conn.close()


def _certify_sweep_winners(
    conn, args: argparse.Namespace, universe: Sequence[str], go_genomes: Sequence[Genome]
) -> None:
    # Chunk U.3: rank the sweep's GO winners by Edge-Certificate score instead of holdout return.
    # The same genome class often GOs on several seeds, so dedupe first; then pool each winner's
    # strictly-OOS ledger (chunk U seams) and certify it (C4 null PENDING — this is a ranking pass,
    # not a final certificate). --certify-out writes the ranked winners as a genomes file that
    # `certify-ensemble --genomes` consumes, so the user no longer hand-picks GO genomes.
    def read(symbol: str) -> pd.DataFrame:
        return db.read_candles(conn, settings.exchange, symbol, args.timeframe)

    unique = _dedupe_genomes(go_genomes)
    print(f"\ncertifying {len(unique)} distinct GO winner(s)...\n")
    funding = _funding_reader(conn)
    rows = []
    for genome in unique:
        eval_pairs = select_eval_pairs(
            genome, read, universe, args.eval_pairs,
            holdout_fraction=args.holdout, seed=args.certify_seed,
        )
        pooled = pool_trades(
            genome, read, settings.taker_fee, eval_pairs,
            window_size=args.window, step=args.step, holdout_fraction=args.holdout,
            read_funding=funding,
        )
        evidence = build_evidence(pooled, seed=args.certify_seed, n_regimes=args.regimes)
        rows.append(CertifiedRow(genome=genome, certificate=certify(evidence, null_beaten=None)))

    print(summarize_certified_sweep(rows))

    if args.certify_out and rows:
        ranked = rank_certified(rows)
        with open(args.certify_out, "w") as fh:
            json.dump([_genome_spec(r.genome) for r in ranked], fh, indent=2)
        print(
            f"\nwrote {len(ranked)} winner(s) to {args.certify_out} "
            f"— feed it to `certify-ensemble --genomes {args.certify_out}`"
        )


def _dedupe_genomes(genomes: Sequence[Genome]) -> list[Genome]:
    """The distinct genomes, order-preserving. The same winner GOs on many seeds; certifying it once
    is enough (and keeps the ensemble file free of duplicates)."""
    seen: list[dict] = []
    out: list[Genome] = []
    for g in genomes:
        spec = _genome_spec(g)
        if spec not in seen:
            seen.append(spec)
            out.append(g)
    return out


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
        embargo = _resolve_embargo(args)
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
                folds=args.folds, embargo_bars=embargo, min_trades=args.min_trades
            ),
            fragility_runs=args.stress,
            graduate_min_trades=args.graduate_min_trades,
            workers=args.workers,
            read_funding=_funding_reader(conn),
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


def _genome_from_spec(spec: dict) -> Genome:
    """Build + validate a Genome from a ``_genome_spec`` dict (the ensemble genomes-file format).
    Missing optional keys fall back to the Genome defaults, so a file can list just family/pair/
    params."""
    genome = Genome(
        family=spec["family"],
        pair=spec["pair"],
        params=spec["params"],
        direction=spec.get("direction", "long"),
        leverage=spec.get("leverage", 1.0),
        trend_period=spec.get("trend_period", 50.0),
        stop_pct=spec.get("stop_pct"),
    )
    validate(genome)
    return genome


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
            read_funding=_funding_reader(conn),
        )
    finally:
        conn.close()

    evidence = build_evidence(pooled, seed=args.seed, n_regimes=args.regimes)
    certificate = certify(evidence, null_beaten=null_beaten)
    print(certificate.summary())


def _certify_ensemble(args: argparse.Namespace) -> None:
    # Chunk Y step 2: certify a PORTFOLIO of frozen winners as its own unit. Reads a JSON list of
    # genome specs (the sweep's GO winners), keeps a decorrelated top-k, unions their strictly-OOS
    # ledgers and judges the pool against the same Edge Certificate. Small edges reach the N>=300
    # floor only aggregated; the ensemble is the deployment unit chunk R allocates.
    with open(args.genomes) as fh:
        specs = json.load(fh)
    candidates = [_genome_from_spec(s) for s in specs]
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
        print(
            f"certifying an ensemble of {len(candidates)} candidates "
            f"(top-{args.k} decorrelated)\n"
        )
        report = certify_ensemble(
            candidates, read, settings.taker_fee, universe,
            k=args.k, eval_pairs=args.eval_pairs, seed=args.seed,
            window_size=args.window, step=args.step, holdout_fraction=args.holdout,
            max_corr=args.max_corr, n_regimes=args.regimes,
            read_funding=_funding_reader(conn),
        )
    finally:
        conn.close()

    print(report.summary())


def _nullcheck(args: argparse.Namespace) -> None:
    # Chunk V: null calibration (C4 of the Edge Certificate). --mode random (V1) scores the
    # candidate's pooled-ledger t_exp against a best-of-M random-genome null over the SAME grid;
    # --mode matched (V2) replays the candidate's OWN trades at random entry times (same count,
    # durations and direction mix) on the SAME series and asks whether its expectancy clears the
    # matched-random distribution — the "is this beta dressed as alpha?" test. Either writes JSON
    # `certify --null` consumes; a data-mined / exposure-only artifact fails to beat its null here.
    genome = _genome_from_args(args)
    conn = db.connect()
    try:
        def read(symbol: str) -> pd.DataFrame:
            return db.read_candles(conn, settings.exchange, symbol, args.timeframe)

        funding = _funding_reader(conn)  # chunk W3 step 2c: real funding for a carry candidate
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
        candidate = build_evidence(
            pool_trades(
                genome, read, settings.taker_fee, eval_pairs,
                window_size=args.window, step=args.step, holdout_fraction=args.holdout,
                read_funding=funding,
            ),
            seed=args.seed, resamples=args.evidence_resamples, n_regimes=args.regimes,
        )
        if args.mode == "random":
            print(
                f"pooling candidate {genome.family} on {len(eval_pairs)} pairs, then "
                f"{args.n_genomes} random genomes over the same grid...\n"
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
                read_funding=funding,
            )
        elif args.mode == "matched":  # exposure-matched random-entry null (V2)
            print(
                f"pooling candidate {genome.family} on {len(eval_pairs)} pairs, then replaying its "
                f"trades at random entry times x{args.resamples} on the same series...\n"
            )
            segments = pool_segments(
                genome, read, settings.taker_fee, eval_pairs,
                window_size=args.window, step=args.step, holdout_fraction=args.holdout,
                read_funding=funding,
            )
            result = random_entry_null(
                candidate.expectancy,
                segments,
                decode_portfolio(genome),
                settings.taker_fee,
                resamples=args.resamples,
                seed=args.seed,
            )
        else:  # surrogate — full re-search on signal-destroyed universes (V3)
            # Load the direct legs once, then for each surrogate block-bootstrap them (destroying
            # the temporal signal but keeping return distribution + cross-leg correlation), run the
            # FULL search on the ratios that rebuild from them, and score the winner by the SAME
            # pooled t_exp as the candidate. Search the full surrogate series (holdout_fraction=0,
            # fragility off): we only need the GA-selected winner, and pool_trades below carves
            # its own OOS windows — so no per-surrogate 200-run graduation is paid. Funding is
            # DELIBERATELY not threaded into the surrogate re-searches (chunk W3 step 2c): a valid
            # null must destroy the carry signal too, so a carry genome collects nothing on
            # signal-destroyed data — the "no edge without real funding" the null should show.
            legs = [p for p in universe if p.endswith(f"/{settings.quote_currency}")]
            leg_frames = {leg: f for leg in legs if len(f := read(leg)) >= 2}
            config = GAConfig(
                population=args.pop, generations=args.gens, seed=args.seed, universe=universe,
            )
            print(
                f"pooling candidate {genome.family} on {len(eval_pairs)} pairs, then re-running "
                f"the search on {args.surrogates} surrogate universes "
                f"(pop {args.pop} x {args.gens} gens, block {args.block})...\n"
            )

            def score_surrogate(s: int) -> float:
                sur_read = surrogate_legs(leg_frames, block_len=args.block, seed=s).__getitem__
                winner = run_search(sur_read, settings.taker_fee, config).best
                pairs = select_eval_pairs(
                    winner, sur_read, universe, args.eval_pairs,
                    holdout_fraction=args.holdout, seed=args.seed,
                )
                pooled = pool_trades(
                    winner, sur_read, settings.taker_fee, pairs,
                    window_size=args.window, step=args.step, holdout_fraction=args.holdout,
                )
                return build_evidence(
                    pooled, seed=args.seed, resamples=args.evidence_resamples,
                    n_regimes=args.regimes,
                ).t_exp

            result = surrogate_null(
                candidate.t_exp, score_surrogate,
                n_surrogates=args.surrogates, seed=args.seed,
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
        "--embargo", type=int, default=None, metavar="BARS",
        help="purge between folds (default scales with timeframe: 1d=5, 4h=30)",
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
        "--embargo", type=int, default=None, metavar="BARS",
        help="purge between folds (default scales with timeframe: 1d=5, 4h=30)",
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
    p_sweep.add_argument(
        "--certify",
        action="store_true",
        help="chunk U.3: after the sweep, pool each GO winner's OOS ledger and rank by Edge-"
        "Certificate score (t_exp) instead of raw holdout return",
    )
    p_sweep.add_argument(
        "--certify-out",
        default=None,
        metavar="FILE",
        help="with --certify: write the ranked GO winners as a genomes JSON (best-first) for "
        "`certify-ensemble --genomes`",
    )
    p_sweep.add_argument(
        "--certify-seed",
        type=int,
        default=0,
        metavar="S",
        help="with --certify: seeds each winner's eval-pair pick + bootstrap (default 0)",
    )
    p_sweep.add_argument(
        "--eval-pairs",
        type=int,
        default=8,
        metavar="N",
        help="with --certify: decorrelated peer pairs pooled per winner alongside its own pair",
    )
    p_sweep.add_argument("--window", type=float, default=0.6, metavar="FRACTION",
        help="with --certify: rolling window size the OOS ledger is pooled from")
    p_sweep.add_argument("--step", type=float, default=0.2, metavar="FRACTION",
        help="with --certify: rolling window step")
    p_sweep.add_argument(
        "--regimes",
        type=int,
        default=2,
        metavar="N",
        help="with --certify: disjoint time regimes for each winner's evidence C5 (default 2)",
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
        "--embargo", type=int, default=None, metavar="BARS",
        help="purge between folds (default scales with timeframe: 1d=5, 4h=30)",
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

    p_ens = sub.add_parser(
        "certify-ensemble",
        help="Chunk Y: pool the top-k DECORRELATED members of a genomes JSON file into one ledger "
        "and certify the portfolio as its own unit (small edges reach N>=300 only aggregated)",
    )
    p_ens.add_argument("--timeframe", default="1d")
    p_ens.add_argument(
        "--genomes", required=True, metavar="FILE",
        help="JSON list of genome specs (family/pair/params[/direction/leverage/trend/stop])",
    )
    p_ens.add_argument(
        "--k", type=int, default=5, metavar="N",
        help="decorrelated members to keep in the ensemble (default 5)",
    )
    p_ens.add_argument(
        "--max-corr", type=float, default=0.7, metavar="R",
        help="drop a member whose daily-P&L correlation with a kept one exceeds this (default 0.7)",
    )
    p_ens.add_argument(
        "--seed", type=int, default=0, help="seeds each member's eval-pair pick + bootstrap"
    )
    p_ens.add_argument(
        "--eval-pairs", type=int, default=8, metavar="N",
        help="decorrelated peer pairs pooled per member alongside its own pair (default 8)",
    )
    p_ens.add_argument("--holdout", type=float, default=0.2, metavar="FRACTION")
    p_ens.add_argument("--window", type=float, default=0.6, metavar="FRACTION")
    p_ens.add_argument("--step", type=float, default=0.2, metavar="FRACTION")
    p_ens.add_argument(
        "--regimes", type=int, default=2, metavar="N",
        help="disjoint time regimes to split the pool into for C5 (default 2)",
    )
    p_ens.set_defaults(func=_certify_ensemble)

    p_null = sub.add_parser(
        "nullcheck",
        help="Chunk V: score a frozen genome vs a null over the same pooled OOS grid (--mode "
        "random = best-of-M random genomes; matched = exposure-matched random entry; surrogate = "
        "full re-search on signal-destroyed data); writes a JSON verdict `certify --null` consumes "
        "as C4",
    )
    p_null.add_argument(
        "--mode", choices=("random", "matched", "surrogate"), default="random",
        help="random = best-of-M random-genome null (V1); matched = exposure-matched random-entry "
        "null on the candidate's own ledger (V2, the 'beta dressed as alpha' test); surrogate = "
        "re-run the FULL search on block-bootstrapped signal-destroyed data (V3, 'is 51% mined?')",
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
        help="[--mode random] random genomes to sample for the null (each pooled over the same "
        "grid; default 50)",
    )
    p_null.add_argument(
        "--resamples", type=int, default=1000, metavar="N",
        help="[--mode matched] random-entry resamples of the candidate's own ledger (default 1000)",
    )
    p_null.add_argument(
        "--surrogates", type=int, default=20, metavar="N",
        help="[--mode surrogate] signal-destroyed universes to re-search for the null (default 20)",
    )
    p_null.add_argument(
        "--block", type=int, default=20, metavar="BARS",
        help="[--mode surrogate] block length for the returns block-bootstrap (default 20)",
    )
    p_null.add_argument(
        "--pop", type=int, default=100, metavar="N",
        help="[--mode surrogate] GA population for each surrogate re-search (default 100)",
    )
    p_null.add_argument(
        "--gens", type=int, default=30, metavar="N",
        help="[--mode surrogate] GA generations for each surrogate re-search (default 30)",
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
