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

- [ ] **F — Live forward feed.** Run a graduated strategy forward in real time off the scraper's
  growing DB (live BarView), same engine contract. Verify: forward replay matches backtest on
  overlapping bars (parity).

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
