---
name: build-roadmap
description: "The chunked plan to finish CoinMonitorSuite — one chunk ≈ one session; source of truth for what's next"
metadata: 
  node_type: memory
  type: project
  originSessionId: d2b51f14-af0b-4701-8a48-a061e92ae8ba
---

The plan to take CoinMonitorSuite from "validated backtester" to "deployable
search→suggest→automate system." Ordered by dependency and the discipline from
[[search-overfits-not-strategy]]: **validate before scaling, search before suggesting,
suggest before any live execution.** Worked one chunk per session — see [[session-build-loop]].
Tick chunks `[x]` as done and add a one-line result. Each chunk ends with a commit message
(user commits — [[user-commits-themselves]]).

**Definition of done for the project:** a Dockerized, k8s-deployable system that backtests +
honestly validates strategies, runs an evolutionary search gated by OOS/walk-forward +
fragility, graduates a survivor through an untouched holdout, emits live trade suggestions, and
(opt-in, safety-gated) auto-executes spot rotations on Bybit.

## Already done (pre-roadmap)
- Phase 1 backtester (black-box engine, SpotPortfolio, metrics) + Phase 1.5 fragility harness.
- Scraper + Streamlit viewer, both Dockerized, writing TimescaleDB ([[backtester-reads-timescaledb]]).
- Walk-forward + **purged** embargo + **OOS fitness function** (`backtest/fitness.py`,
  `evaluate_fitness`) — the GA's scoring substrate. (2026-06-28)

## Chunks (in order)

- [x] **A — Real-data validation run.** (2026-06-28) Backfilled SOL/BNB/XRP daily; scored fixed
  genome OOS across 8 daily series + purged WF + fragility. **Verdict: pulse is pair-specific** —
  garbage on most pairs, real fragility-robust risk-adjusted edge on XRP ratios (XRP/ETH +34% mean
  OOS, all 4 folds positive, fragility 100% positive, Calmar 3.40 > B&H 2.55). Two carry-forwards:
  **(1) make pair/universe a gene; (2) the fitness symmetric-std penalty is miscalibrated** (scores
  all-folds-positive XRP/ETH below zero) — switch to downside/negative-fold penalty before the GA.
  See [[chunk-a-findings]] and docs/lessons-learned.md. (O(n²) engine is the binding GA constraint.)

- [x] **B — Genome representation.** (2026-06-28) `coinmon/search/genome.py`: `Genome(family, pair,
  params)` + `FAMILIES` registry (rsi_meanreversion, ema_crossover) with `ParamSpec` ranges +
  `UNIVERSE` pair pool + `decode()` → `make_strategy` factory the fitness rig already accepts. Pair is
  a gene (chunk-A). **Fitness penalty fix landed**: `evaluate_fitness` now docks `downside_dev =
  sqrt(mean(min(0,foldₜ)²))` instead of symmetric std, so an all-folds-positive genome pays zero
  instability (XRP/ETH no longer scored below zero). 63 tests green. Next: chunk C wires `decode` +
  pair→candles (extract CLI `_load_candles`) into the GA loop.

- [x] **C — Evolutionary search loop.** (2026-06-28) `search/ga.py` = pure, seed-deterministic GA
  mechanics (`random_genome`/`mutate`/`crossover`/`tournament_select`/`evolve`, elitism + fitness
  memoization), I/O-free and taking a caller-supplied `fitness(genome)->float`. `search/runner.py`
  wires it to real data: `CandleCache` (per-pair, resolves ratios via the extracted
  `data/candles.load_candles`), scores each genome with OOS `evaluate_fitness`, then runs the
  fragility kill-filter on the **winner only** as a post-filter gate (`fragility_verdict`,
  `fraction_positive >= min`) — fragility stays OUT of per-genome fitness because the O(n²) engine
  is the binding constraint. Bad/short pairs score `-inf` and are discarded. CLI `coinmon search`
  (pop/gens/seed/folds/embargo/min-trades/stress). 78 tests green. Verified in unit tests: GA climbs
  a synthetic objective; fragility gate thresholds correctly. **Not yet run against the live DB** —
  the "reject garbage on real data" proof is a user run (`coinmon search --timeframe 1d --stress N`,
  Docker DB up). Next: chunk D graduation gate (untouched holdout + full fragility → go/no-go).

- [x] **D — Graduation gate.** (2026-06-28) `search/graduation.py`: `graduate(genome, holdout, …)`
  runs the GA winner on a never-searched holdout tail + full fragility, returns a hard go/no-go
  `GraduationReport` with explicit `reasons` (gates: holdout return > 0, ≥ `min_trades` holdout
  trades, fragility `fraction_positive ≥ min`; B&H reported, not gated). `data/candles.split_holdout`
  carves the last `holdout_fraction` of each pair *before* evolution. `run_search` gained
  `holdout_fraction` (default 0 = unchanged chunk-C): when > 0 the GA scores only the search head
  and graduation supersedes the chunk-C fragility post-filter. CLI `search --holdout FRACTION
  --graduate-min-trades N`. 88 tests green (garbage genome → NO-GO with reasons; robust edge → GO).
  **Not yet run against the live DB** — the real graduation proof is a user run
  (`coinmon search --timeframe 1d --holdout 0.2 --stress 80`). Next: chunk E (feature store, only if
  GA is compute-bound) or chunk F (live forward feed).

- [ ] **E — Indicator/feature-store engine (conditional).** Only if the GA is compute-bound:
  precompute fixed-menu indicators to DB, serve `BarView.features` point-in-time ([[feature-store-seam]]),
  strategies take the fast path. Own Docker container. Verify: identical results vs recompute, big speedup.

- [x] **F — Live forward feed.** (2026-06-28) Extracted the engine's per-bar state machine into a
  shared `BarStepper`/`StepResult` (`backtest/engine.py`): the fill→mark→decide core, now used by
  both `BacktestEngine.run` and the live feed so they decide+fill IDENTICALLY (**parity by
  construction**, not a duplicated loop). New `coinmon/live/`: `LiveFeed` (incremental DB reader —
  re-resolves the pair incl. synthetic ratios via `load_candles`, returns only bars past a
  watermark, so each closed bar drives the strategy exactly once across many polls; scraper stores
  only closed bars so no partial-bar guard needed) and `ForwardRunner` (drives one strategy via
  `BarStepper`, state persists across polls). CLI `coinmon forward --strategy --symbol --timeframe
  [--follow --interval]`: one-shot replay of stored bars + optional poll loop. 94 tests green —
  parity proven two ways (scripted + RSI on a real series: forward equity curve & trade list ==
  `BacktestEngine`) and **batch-invariant** (multi-poll == one-shot). Genome→strategy on the CLI
  still uses the `STRATEGIES` dict (no graduated-genome persistence yet — that lands with G/H).
  Next: chunk G (suggestions service) — *blocked on delivery channel*.

- [x] **K — Directional capability (perp short).** Inserted ahead of G after the gate-decision
  resolved toward *adding a bearish leg*, not softening the gate (see [[perp-short-capability]] and
  [[first-live-search-graduation]]). **K1 done (2026-06-28):** `PerpPortfolio` (long/flat/short,
  isolated all-in leverage, notional-based taker fees, close-bar liquidation latch), engine/
  `BarStepper` generalized to a 3-state position (-1/0/+1; spot 0/1 path byte-unchanged, parity
  green), `strategies/directional.ShortWhenFlat` (flat→short). Proof test: long/flat spot bleeds on
  a downtrend while ShortWhenFlat+PerpPortfolio profits. **K2 done (2026-06-28):** direction is now
  a GENE — `Genome` gained `short: bool` + `leverage: float` (default long/flat spot = chunk-B
  unchanged), `LEVERAGE=ParamSpec(1,5)`; `decode` wraps in `ShortWhenFlat` when short, and a NEW
  `decode_portfolio(genome) -> (cash, fee) -> Portfolio` yields the perp-vs-spot book. Threaded the
  portfolio factory through the rig that previously hard-built `SpotPortfolio`: `evaluate_fitness`
  gained an optional `make_portfolio` (defaults to spot, back-compat), `runner` (`_score_genome` +
  fragility post-filter) and `graduation` now pass `decode_portfolio(genome)`. GA samples/mutates/
  crosses the direction genes and `_key` includes them (no long/short memo collision). Summaries
  surface `[Lx perp short | long/flat spot]`. 113 tests green, ruff clean (only pre-existing
  walkforward/viewer E501s remain, untouched); proof test: same RSI genome out-returns its spot twin
  and graduates GO on a synthetic downtrend. **CLI search now explores direction by default** — the
  GA can finally pick a short winner. **First live run done (2026-06-28):** `search --timeframe 1d
  --holdout 0.2 --stress 80` → GA winner `atr_channel XRP/ETH 4.6x perp short`, graduation **NO-GO**
  (holdout -99%, fragility 0%). The gate correctly rejected a leveraged blow-up (safety intact), but
  it surfaced [[leverage-breaks-fitness-scaling]]: the OOS fitness is calibrated for spot returns, so
  leverage inflates the median + floors downside at liquidation → the SEARCH is pulled toward
  reckless leverage and its winner almost always NO-GOs. **Follow-up (before the downtrend-GO can be
  claimed): recalibrate fitness** — disqualify liquidating folds + reward risk-adjusted (not raw)
  return, and/or tighten the leverage range. Code/plumbing for K is done; the fitness fix is chunk L.

- [x] **L — Risk-shaped search (stop-loss gene + convex drawdown penalty).** The fix for
  [[leverage-breaks-fitness-scaling]]: keep leverage a free gene but make ruin expensive, and give the
  bot a brake. User decided (2026-06-28): the multiplier lives in FITNESS only (equity stays a
  truthful exchange mirror — no synthetic loss debit, preserves live-parity), and the stop triggers
  INTRABAR on each bar's low/high (not close). **Part B done (2026-06-28):** `evaluate_fitness` now
  subtracts a convex `drawdown_penalty` anchored to recovery asymmetry `g(d)=d/(1-d)` — the WORST
  fold's max drawdown beyond `drawdown_band=0.30` is charged `g(d)-g(band)`, capped finite at d=0.99
  so a liquidating fold (d=1) is catastrophic (~98) without inf-breaking GA ordering; new
  `_recovery_gain`/`_drawdown_penalty` + FitnessResult fields (`worst_drawdown`, `drawdown_penalty`,
  `fold_drawdowns`) + summary. 117 tests green, ruff clean. **Live proof it works:** same
  `search --timeframe 1d --holdout 0.2 --stress 80` → winner leverage **4.6x → 2.5x**, gen-0 mean
  fitness **-1.08 → -47.7**, holdout **-99% → -39.7%** (leverage NOT capped — the GA chose less of it
  because tail risk now costs). Still NO-GO though: the winner kept a 74%-DD fold because its +429%
  raw leveraged median outweighs the -2.48 penalty → **Part A is the missing brake.** **Part A (next):**
  intrabar stop-loss as a GENE (threshold the GA tunes), enforced in the engine/perp book against bar
  low/high, force-closing at the stop level mid-bar — must sit OUTSIDE `ShortWhenFlat` and latch flat
  (the existing `strategies/stop_loss.py` is long-only, exits at next-open, and would re-short through
  the wrapper, so it can't be reused as-is). **Part A done (2026-06-28):** the intrabar stop is a gene
  enforced in the SHARED engine core (`BarStepper.stop_pct`), not a Strategy wrapper — so it fills
  mid-bar at the stop level, which a next-open signal can't. After the open fill it checks the bar's
  low (long) / high (short) against `entry*(1∓stop_pct)`, force-closes flat at that level (routed
  through the execution model, so the stop slips under fragility like any fill), latches the stopped
  side, and `_guard_reentry` keeps it flat while the strategy keeps demanding that side — resuming the
  moment the signal flips/resets (default flat-and-wait, generalized to 3-state so a stopped-out short
  waits for a long flip). `Genome.stop_pct: float|None` + `STOP=ParamSpec(0.02,0.50)`; **None is
  first-class "no stop" and the GA reaches it** (coin-flip sample, `_mutate_stop` arms/disarms,
  crossover/`_key` carry it) — because a stop HURTS some families ([[stop-loss-hurts-mean-reversion]])
  so "off" must be selectable. Threaded `stop_pct` through `evaluate_fitness`/`run_monte_carlo`/
  `graduate`/`runner`/`ForwardRunner` from `genome.stop_pct` (engine stays genome-agnostic; default
  None = byte-unchanged spot/perp path, parity preserved). 127 tests green (+10), ruff clean (only
  pre-existing walkforward/viewer E501s). Engine proofs: a 10% stop caps a long's loss at the stop
  level and **prevents a 3x short liquidation** (survives at 70 vs 0); suppression latch verified
  bar-by-bar. **Live downtrend-GO proof is the next user run** (`search --timeframe 1d --holdout 0.2
  --stress 80`): expect the GA to pair leverage with a protective stop and finally graduate GO. A
  risk-adjusted (return/drawdown) fold metric stays a fallback if the stop alone doesn't close it.

- [x] **M — Regime-adaptive direction.** (2026-06-28) The fix for [[direction-gene-overfits-regime]]:
  the fixed `short` gene was chosen in-sample and blind to the holdout regime, so every live NO-GO was a
  wrong-direction bet. User decided: REPLACE `short: bool` with `direction ∈ {long, adaptive}` (overfit
  vector removed, not just reachable) and make the regime window a searchable gene. New
  `strategies/directional.RegimeAdaptive(base, trend_period)` reads a point-in-time SMA of seen closes —
  up-regime (close ≥ SMA) runs the base long/flat (won't short a rising holdout), down-regime applies
  `ShortWhenFlat` (shorts the would-be-flat legs, rides a falling holdout); reuses the same ShortWhenFlat
  instance and calls the base exactly once/bar. `Genome.direction`/`trend_period` (TREND=ParamSpec(20,200),
  inert when long); `decode`→RegimeAdaptive+perp; GA sample/mutate/cross + `_key`; summaries say
  "Lx perp regime-adaptive (MA…)". `direction="long"` is byte-unchanged spot (parity). 131 tests green
  (+4), ruff clean (only pre-existing walkforward/viewer E501s). **Live downtrend-GO proof is the next user
  run** (`search --timeframe 1d --holdout 0.2 --stress 80`): does reading the holdout's own regime finally
  graduate GO where the fixed gene NO-GO'd? Caveat: not guaranteed on a *choppy* crash ([[chunk-l-live-validation]]).
  **VALIDATED LIVE (2026-06-28): first search-winner GO ever** — winner `rsi_meanreversion BNB/ETH 1.0x perp
  regime-adaptive (MA47), 38% stop` graduated **GO** (holdout +2.92%/134 bars, 13 trades, fragility 100%) on
  the SAME +13.65% up-regime where the fixed-short gene NO-GO'd by shorting the rise. Direction now reads the
  holdout's own trend. Caveats: one seed (0); trails B&H; choppy-crash case still unproven (winner was up-regime).
  See [[direction-gene-overfits-regime]] (RESOLVED). **10-seed sweep then run** → 4 GO / 6 NO-GO: the GATE is a
  validated trustworthy judge (discriminates direction/evidence/robustness) but durable ALPHA is unproven (all
  GOs are thin-trade leveraged crash-shorts on one down-regime). Next: raise `--graduate-min-trades` to ~15–20,
  test across regimes, forward-test. See [[regime-adaptive-multiseed-sweep]].

- [ ] **N — Scale the search (now that the JUDGE is validated).** The sweep ([[regime-adaptive-multiseed-sweep]])
  proved the gate is a trustworthy judge but alpha is unproven on a tiny search. User's call: make the search
  fast + strict + bigger, IN THIS ORDER (speed → strictness → surface, so the stricter judge is already in place
  before the surface is flooded — adding surface first just manufactures false GOs). **Done one part per session.**
  - [x] **N1 — Incremental indicators (O(n²)→O(n)).** (2026-06-28) THE perf win: strategies recomputed each
    indicator over the whole `_closes` buffer every bar (`rsi(pd.Series(self._closes),…).iloc[-1]`) → O(n²), the
    binding constraint since chunk A. Added `StreamingEMA`/`StreamingRSI`/`StreamingATR` (+ `_WilderStream`) to
    `indicators/__init__.py`: O(1)/bar, **bit-identical** to the pandas functions' `.iloc[-1]` per bar — each
    replicates the exact arithmetic (ewm adjust=False recurrence `old*prev+new*x` ÷ `(old+new)`; Wilder = numpy-mean
    SMA seed then recursive). The 3 strategies (rsi_meanreversion/ema_crossover/atr_channel) now drive the streaming
    objects instead of recomputing; the `view.feature()` fast path is kept and live-parity is preserved (same
    Strategy object). 145 tests green (+14: bit-parity vs full-series recompute, exact `==`, periods 2–40).
    **Measured: 5380× faster at n=4000** (gap widens with n; O(n²)→O(n)), bit-parity confirmed. Changed files
    ruff-clean (pre-existing walkforward B905 + walkforward/viewer E501 untouched). Next: N2 (CPU multiprocessing).
  - [x] **N2 — CPU multiprocessing.** (2026-06-28) Fanned the per-genome fitness map across a process pool while
    keeping the GA's RNG stream serial in the parent — `ga.evolve` gained an optional `score_batch` (default = serial
    map; the GA still memoizes + intra-batch dedups, so workers never re-score a known genome), and `search/parallel.py`
    (`ParallelScorer`/`WorkerContext`/`_score_one`) runs a `ProcessPoolExecutor` whose order-preserving `map` makes
    parallel **bit-identical to serial** (proven by a real-spawn test). Windows spawn handled by preloading the whole
    UNIVERSE in the parent and shipping the picklable candle dict to each worker via the pool initializer (no DB/conn
    in workers); the worker reuses the runner's exact `_score_genome`. `run_search(workers=…)` (0 = all cores, 1 =
    byte-unchanged serial) + CLI `search --workers N`. 148 tests green (+3), ruff clean. **Measured (12 cores):**
    speedup depends entirely on per-genome cost now that N1 made it cheap — at small/daily scale spawn+IPC overhead
    makes parallel *slower* (~0.4×), but at a heavy load (6000 bars, pop 80, gens 12, 8 folds) it's **2.61× faster**,
    identical results. Sub-linear because of Windows spawn cost, the per-generation serial barrier (RNG selection idles
    workers between gens), and memoization shrinking the parallelizable set. **So default stays serial; the win is
    reserved for the heavy regimes N4 (100 pairs) and Q (tree-GP) push toward.** See [[n2-parallelism-overhead]].
    (GPU/4060 deferred — it needs a vectorized batch-engine rewrite that breaks live-parity; only worth it after O(n²)
    is gone and we're still compute-bound at 100k-genome scale.)
  - **N3 — Stricter gate: min-trades → 15.** Trivial (`graduate_min_trades` default), high signal: the sweep's
    GOs were thin-trade (5–7) low-evidence genomes; 15 forces real sample size. "Maybe more later."
  - **N4 — Expand the pair universe (~12 → ~100).** REALITY: ~100 pairs = scrape ~12–15 base coins, then ratios
    combine (C(14,2)≈91 + 14 USDC) via the existing synthesis — auto-generate UNIVERSE from available symbols, not
    100 feeds. CAVEAT (load-bearing, [[search-overfits-not-strategy]], [[chunk-a-findings]]): more pairs = more
    independent holdouts to fish in = MORE overfit surface / more lottery tickets, so a GO-among-100 is WEAKER
    evidence than a GO-among-12, not stronger. Treat as a throughput/scale test, not "more pairs = more alpha".
    Budget for data hygiene (illiquid alts have gaps/bad prints that poison ratio alignment). Eventually the gate
    needs pair/regime-robustness (survive >1 pair / across up-down-chop holdouts), not just absolute return on one
    tail. This is the END-GOAL substrate for "full Bybit portfolios" in the prod-v1 deploy (user will buy HW for
    that; the workstation is the test rig).
  - **N5 — Tier-1 incremental indicator library.** Add streaming O(1) indicators following N1's pattern: EMA/DEMA/
    TEMA, MACD, RSI, ATR, ADX/DMI, TRIX/TSI, Parabolic SAR, SuperTrend, OBV/AD/PVT, Force Index/Elder Ray. (User's
    Tier 1/2/3 taxonomy is correct; Tier 1 only for now.) **BUT** indicators are dead weight unless a representation
    CONSUMES them — current system is a GA over ~3 fixed strategy templates, NOT genetic programming. "More room to
    be wrong" really points at a future **tree-GP** (genomes = expression trees composing the indicator pool with
    operators). Until that exists, N5 means adding strategy FAMILIES that use the new indicators, family by family.
    Name the tree-GP target so the library has a real payoff.
  - **N6 — Bigger multi-seed sweep (the payoff test).** Once fast+strict+bigger: run many seeds and see whether
    GOs survive the 15-trade floor and a 100-pair surface — i.e., is there signal, or just more lottery winners?

- [ ] **O — Extreme judge: cross-pair robustness gate.** (user idea, post-N6) If N6 yields GOs, harden the gate
  before growing the search surface (P/Q): a GO is only confirmed if the SAME genome — pair gene overridden —
  still holds up on **≥K of N (≥3) randomly-picked, decorrelated** pairs. This directly kills the lottery-ticket /
  pair-specific-overfit failure mode ([[chunk-a-findings]] "pulse is pair-specific"; the sweep's GOs hopped pairs
  by seed): a structural edge generalizes across coins, a holdout-luck curve-fit doesn't.
  **METRIC CORRECTION (REVISIT with user):** user proposed "profitability holds ±10% of the original GO result."
  Rejected as-is — returns DON'T match across pairs of different volatility/regime (±10% of a +2.92% number is an
  impossibly tight band; ±10pp is arbitrary), so a magnitude-match would reject genuinely robust edges. Correct
  invariant = **sign/profitability persistence**: stays positive + fragility-positive + clears min-trades on ≥K of
  N pairs. Stretch: a risk-adjusted band (Calmar / return-vs-B&H) instead of raw sign. Catches: random pairs must
  be DECORRELATED (3 majors crashing together ≠ 3 independent tests); seed the pick for reproducibility.
  **TAG, don't reject (user refinement):** the cross-pair run is a CLASSIFIER, not a filter — label the GO
  `golden` (held up on ≥K of N decorrelated pairs → structural, high-trust, core capital) vs `specialist`
  (graduated on its own pair only → tailored, lower-trust, conditional capital). Both stored + allowed; this
  rescues the real pair-specific alpha chunk A found (XRP ratios) instead of discarding it. Cheap to add — O
  already runs the N pairs, just record the pass-count + label. The TIER is what P/Q and the allocator (R) trust.
  This is still the "meaner judge" that must exist BEFORE P/Q — it's now the trust-DISCRIMINATOR, not a kill gate.

- [ ] **P — Bounded multi-indicator genome (risk-managed GP half-step).** Before unbounded trees, a FIXED-shape
  genome that picks 2–3 indicators from the Tier-1 pool (N5) + thresholds + a combine rule (AND/OR). Far more
  expressive than the 3 hand-built templates (the MACHINE composes, not us), but the surface is CAPPED → bloat is
  impossible and the overfit surface grows by a controlled, watchable amount. Reuses the `decode → Strategy`
  contract: the genome compiles to a Strategy that interprets its (indicator, threshold, op) spec per bar,
  point-in-time (no lookahead). **Verify:** does the now-cross-pair-hardened gate (O) hold its false-GO rate
  against this bigger-but-bounded surface? If yes → earned the right to go unbounded (Q). If no → the judge needs
  more work before tree-GP, discovered cheaply without building the whole tree machinery.

- [ ] **Q — Full tree-GP (the endpoint).** Genomes = typed expression trees over the indicator pool + operators /
  constants / price-fields; a strongly-typed grammar so crossover can't make `RSI(close > 30)` garbage; subtree
  crossover + subtree/point mutation; **bloat control** (depth/size caps + parsimony pressure in fitness — the
  classic GP tax). Reuses the ENTIRE eval rig unchanged (it's representation-agnostic — consumes
  `make_strategy: () -> Strategy`; a tree just compiles to a Strategy). This is the "give the GP room to be wrong"
  goal: the machine composes indicators into programs instead of us hand-writing families. **GATED ON:** N1/N2
  (GP multiplies eval cost — trees are pricier, bloat, bigger pops/gens; the O(n²) engine must be gone first) AND
  O (GP is a vastly stronger overfitting engine; the single-holdout gate validated against a 6-gene GA would get
  rubber-stamped to death without the meaner judge) AND ideally P's evidence that the gate scales. Nothing here is
  architecturally blocked today — the blocker is JUDGE-READINESS + SPEED, not plumbing.

- [ ] **R — Tiered, regime-conditional allocation (deployment policy).** (user idea) A multi-strategy book on top
  of the O tags: a `golden` (structural) CORE plus `specialist` (pair-tailored) sleeves, with capital allocated by
  trust tier and conditions — like a real multi-strat fund. Two halves, NOT equally safe:
  - **Defensive (build first, robust):** a coarse, slow global RISK-OFF detector (broad-market drawdown / vol
    spike / cross-asset correlation spike) de-weights the fragile specialists and leans on golden. Being wrong
    just means too cautious. Safe default.
  - **Offensive (gated, DANGEROUS):** "deploy a specialist because its pair is booming" is the direction-overfit
    trap one level up — a point-in-time REGIME PREDICTION that assumes the boom continues (non-stationarity, the
    thing that killed every earlier NO-GO). The specialist was fit to a boom that already happened. So the
    specialist-ON trigger is a META-STRATEGY that must be backtested + gated like any other, NOT a heuristic
    trusted because it sounds reasonable. Treat "when to turn a specialist on" with the same suspicion as "which
    direction to bet."
  - **Continuous, not binary:** allocate capital by trust tier and scale specialist size down as conditions
    deteriorate (a dial, not a core↔specialist toggle) — graceful degradation, not a regime coin-flip deciding all.
  - **Deployment-phase, parked:** sits on the live suggestions/executor (G/I) and only matters once O produces
    golden + specialist GOs to allocate between. We have ZERO confirmed alpha — do NOT build this before there are
    strategies to allocate. Planned now, built later.

- [ ] **G — Phase 2: suggestions service.** Service runs the graduated strategy live (paper) and
  emits trade suggestions; no execution. Dockerized; FastAPI control-plane begins.
  *Blocked on: how suggestions are delivered (log/webhook/Telegram/UI).* Verify: emits a correct
  rotate signal on a known historical replay.

- [ ] **H — Control-plane API + minimal UI.** FastAPI (strategies, results, suggestions, search
  runs) + minimal React/TS UI. Dockerized. Verify: endpoints return live state; UI renders it.

- [ ] **I — Phase 3: automated execution.** Bybit order path behind the ExchangeAdapter order API
  (same contract as the sim), sequential two-leg rotation with real gap. Testnet/paper first, then
  tiny live. Safety: dry-run default, kill switch, position/loss limits. *Blocked on: testnet vs
  live, capital cap — ASK, high risk.* Verify: testnet round-trip rotation executes + reconciles.

- [ ] **J — k8s packaging.** Dockerfiles for every component (engine/search/API/executor),
  Helm chart or manifests, ConfigMaps + Secrets for API keys ([[deployment-target-k8s]]).
  Verify: `helm template`/manifests apply clean; a component runs in-cluster.

## Notes
- **Money safety (hard line the user cares about):** chunks A–H and J place **no orders and risk
  no money** — they only read data and simulate (F/G use read-only public market data, no keys).
  **Chunk I is the only place real money can enter**, and it defaults to dry-run → testnet → tiny
  live, gated behind explicit user opt-in + capital cap. Trade-permission API keys do not exist in
  the system until I, so nothing before it can physically trade.
- Chunks A and the analysis chunks need the user to start Docker Desktop (DB on host port 5433;
  set `COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon`).
- Re-scope freely as findings land (e.g. if chunk A shows no pulse, the GA chunks pivot to
  proving the rig rejects garbage rather than chasing alpha). Keep this list honest.
