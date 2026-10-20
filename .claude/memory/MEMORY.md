# CoinMonitorSuite Project Memory

This file indexes all memory files. One line per file; detail lives in each topic file.

## Read first — mission & standing directives
- [mission-find-edge-ship-ui](mission-find-edge-ship-ui.md) — **THE MISSION: ≥3 winner strategies → UI → confirmed/auto trading; ~$10 micro-live OK for the first promising one**
- [live-yield-hurdle](live-yield-hurdle.md) — **USER GATE: certified ≠ deploy; real capital needs FORWARD net yield ≥5%/yr (recent regime weighted)**
- [riskier-strategies-allowed](riskier-strategies-allowed.md) — **2026-07-18: riskier OK (drawdown/variance only); ≥5%/yr floor + honesty stand; anomaly-first hunting**
- [anomaly-hourofday-lead](anomaly-hourofday-lead.md) — 21-23 UTC session-close effect: B20 OOS pass but maker-fee-only → maker-execution bet, needs live paper
- [fuck-it-we-ball-mode](fuck-it-we-ball-mode.md) — **2026-07-31: EXTREME strategies authorized for Fable-approved ideas; exotic venues/plumbing in scope**
- [fable-batch-10-probe-queue](fable-batch-10-probe-queue.md) — **THE QUEUE: Fable's 10 ideas w/ pre-registered PASS/KILL; per-idea STATUS lines inside (most KILLED)**
- [bybit-dropped-no-eu-leverage](bybit-dropped-no-eu-leverage.md) — **2026-10-09: Bybit dropped (EU = spot-only); execution venue LOCKED = HYPERLIQUID**
- [bybit-only-leverage-doctrine](bybit-only-leverage-doctrine.md) — (venue superseded) leverage-class caps still reusable; MiCA/USDC-only universe conflict
- [cursed-100-eur-live-ladder](cursed-100-eur-live-ladder.md) — **the cursed 100 EUR → F8 cascade ladder live, data-gathering not deployment; owner's leverage call, don't re-litigate**
- [live-bot-dashboard-plan](live-bot-dashboard-plan.md) — **F8 bot + web dashboard LIVE on Hyperliquid mainnet since 2026-10-13; budget fix deployed (~200-300 actions/day, buffer out ~mid-Nov). Burn meter + ☠ graveyard built 2026-10-20 (add a grave per probe in web/src/strategies.ts). Owed: agent-can't-withdraw proof, PANIC w/ position, death alert**
- [ui-trader-terminal-look](ui-trader-terminal-look.md) — **owner's UI bar: pro trader-terminal web app (Streamlit rejected); screenshot-check before done**
- [no-strategy-preference](no-strategy-preference.md) — ZERO strategy preference; only "certified/winnable" matters
- [no-more-rsi-ema-permutations](no-more-rsi-ema-permutations.md) — price-transform indicator strategies exhausted; baseline/control only
- [ga-parked](ga-parked.md) — **GA HARD-BANNED: never `coinmon sweep`/`search`; tuning = exhaustive recorded grid + holdout (see F8 grid)**
- [honest-status-reporting](honest-status-reporting.md) — never claim done without artifact evidence; surface scope downgrades loudly
- [no-multi-hour-data-loads](no-multi-hour-data-loads.md) — **USER RULE: no multi-hour backfills; estimate load time before launching**
- [confidential-memory-split](confidential-memory-split.md) — **owner infra/identities/balances ONLY in gitignored `confidential/` ([INDEX](confidential/INDEX.md)); never secrets**
- [user-commits-themselves](user-commits-themselves.md) — never run git commit; hand over a commit message and stop
- [session-build-loop](session-build-loop.md) — session shape: read memory → next chunk → ask blockers → commit message

## Current status & results (still 0 deployable winners)
- [h1-hl-funding-carry-killed](h1-hl-funding-carry-killed.md) — **H1 HL carry KILLED 2026-10-20 (2x iso: 44 wick liqs); but HL funding NOT decayed: +13%/yr hedged notional, 3-9pp > Binance; post-hoc lead = portfolio margin**
- [f8-cascade-ladder-result](f8-cascade-ladder-result.md) — **F8 PASS 4/4 spot+perp; recent hurdle clear rests on touch-fills. F8S short mirror KILLED. Param grid 2026-10-19: KEEP 2.5/1.2/60 (train pick +6.8%/yr on holdout, CI spans 0)**
- [f4-unlock-short-killed](f4-unlock-short-killed.md) — **F4 unlock short KILLED 2026-10-19 (+1.08%/event, CI spans 0, no placebo beat); post-hoc cliff-only +4.3% needs forward data. Z2: DB has ALL Binance USDT-M perps incl. delisted (1d + funding)**
- [f11-post-listing-drift-killed](f11-post-listing-drift-killed.md) — F11 post-listing drift short KILLED 2026-10-15 (~26% of listings double → 1x short liquidated)
- [f9-weekend-vrp-killed](f9-weekend-vrp-killed.md) — F9 weekend VRP KILLED on real Deribit prints; DVOL pass was the calendar effect
- [f7-f3-killed](f7-f3-killed.md) — F7 clock scalp + F3 quarterly basis KILLED; structural premia 2021-22-fat, recent-dead
- [f6-new-listing-funding-killed](f6-new-listing-funding-killed.md) — F6 new-listing funding KILLED both venues; mean is a tail
- [f5-polymarket-favorites-killed](f5-polymarket-favorites-killed.md) — F5 Polymarket favorites KILLED (gap −1.53pp) + API gotchas
- [bybit-liquidation-collector](bybit-liquidation-collector.md) — allLiquidation collector RUNNING since 2026-10-08 (22h outage 10-08/09); 'Buy' = long liquidated; read only inside coverage spans
- [f1-tail-gated-carry-result](f1-tail-gated-carry-result.md) — F1 PASS 5/5 but recent-24mo acct +2.47%/yr → misses hurdle; use as capital-light overlay
- [w3-carry-first-live-diagnosis](w3-carry-first-live-diagnosis.md) — W3 carry CERTIFIED (first cert) +2.23%/yr; parked under the yield hurdle; 4h refuted
- [b13-low-vol-fresh-lead](b13-low-vol-fresh-lead.md) — low-vol lead CLOSED; short leg was survivorship-suspect (pre-Z2 DB had 0 delistings)
- [session-2026-07-18-tsmom-oi](session-2026-07-18-tsmom-oi.md) — B17 TSMOM refuted; OI collector built (open_interest table); B18/B19 OI signals FAIL
- [b16-funding-signal-refuted](b16-funding-signal-refuted.md) — B16 cross-sectional funding-crowding REFUTED
- [certified-sweep-calibrated-negative](certified-sweep-calibrated-negative.md) — chunk Y payoff sweep: 0 CERTIFIED; price-shape valley empty
- [xsectional-momentum-first-run](xsectional-momentum-first-run.md) — W5 X-sectional momentum NOT a winner (best-of-162 REFUTED)

## Plan B (new inputs) & Plan C
- [plan-b-fallback-probes](plan-b-fallback-probes.md) — Plan B: probe NEW INPUTS (B1–B12); collectors start immediately
- [plan-b-p1-results](plan-b-p1-results.md) — P1 (B1–B4) all FAIL; candle-shape signals exhausted
- [plan-b-p3-results](plan-b-p3-results.md) — P3: B10 maker-hurdle FAIL; B9 `MakerLimitExecution` infra built, runner deferred
- [order-flow-direction](order-flow-direction.md) — taker delta / OI / long-short candidates; L2 imbalance rejected
- [order-flow-probe-h7-refuted](order-flow-probe-h7-refuted.md) — H7 taker-flow/CVD REFUTED (next-bar IC≈0)
- [liquidation-cascade-fade](liquidation-cascade-fade.md) — post-cascade reversal idea; record liquidations early, pool symbols
- [onchain-stablecoin-netflow](onchain-stablecoin-netflow.md) — stablecoin netflow signal; lowest priority, paid data
- [plan-c-onchain-ideation](plan-c-onchain-ideation.md) — IDEATION only: DEX insider accumulation before listing; parked

## Methodology & rig
- [alpha-definition-edge-certificate](alpha-definition-edge-certificate.md) — THE alpha definition: pooled-OOS Edge Certificate (N≥300, CI>0, beats nulls, ≥2 regimes)
- [portfolio-search-protocol](portfolio-search-protocol.md) — post-GA: exhaustive small grid, ALL recorded, deflated, holdout once
- [strategy-lab-model](strategy-lab-model.md) — the evaluator is the product; chunk vs Plan namespace decoder
- [train-usdt-certify-usdc](train-usdt-certify-usdc.md) — search on USDT, certify on pristine USDC; Binance = history only
- [fragility-stress-test](fragility-stress-test.md) — Monte Carlo latency/slippage stress as kill-filter before live
- [autotrading-rollout](autotrading-rollout.md) — suggest-only → auto-on-confirm → capped full-auto
- [search-overfits-not-strategy](search-overfits-not-strategy.md) — the param SEARCH overfits (−23% OOS) while fixed params survive (+12%)
- [nested-holdout-refutes-golden](nested-holdout-refutes-golden.md) — nested holdout refuted the "golden" edge; gate is defensive not alpha
- [regime-adaptive-multiseed-sweep](regime-adaptive-multiseed-sweep.md) — gate is a trustworthy judge; durable alpha unproven
- [walk-forward-stability-harness](walk-forward-stability-harness.md) — `coinmon stability`: rolling re-search persistence; diagnostic only
- [first-stability-run-expanded-universe](first-stability-run-expanded-universe.md) — first stability run: clean calibrated NEGATIVE

## Environment, data & infra
- [project-direction](project-direction.md) — Python greenfield, phased backtest→suggestions→automation; USDC quote constraint
- [backtester-reads-timescaledb](backtester-reads-timescaledb.md) — candles come from TimescaleDB (`db.read_candles`), not Parquet
- [data-package-gitignored](data-package-gitignored.md) — `data/` gitignore once swallowed `src/coinmon/data/`; now anchored `/data/`
- [deployment-target-k8s](deployment-target-k8s.md) — k8s + Docker images; Helm chart `deploy/helm/coinmon`, GHCR via `build.yml`
- [user-infra-ui-plans](user-infra-ui-plans.md) — user-owned k8s/central DB; keep tables merge-friendly (natural keys)
- [ui-roadmap](ui-roadmap.md) — three UI tiers gated on data existing
- [machines-and-tooling](machines-and-tooling.md) — multiple machines; verify the stack runs before promising runs
- [feature-store-seam](feature-store-seam.md) — BarView point-in-time feature contract; indicator engine deferred
- [build-roadmap](build-roadmap.md) — the chunked build plan (historical source of "what's next")
- [prototype-reference](prototype-reference.md) — the .NET prototype in C:\Dev\CoinMonitor; patterns to reuse
- [user-quant-background](user-quant-background.md) — limited quant math; relies on the eval rig
- [blackbox-evolutionary-vision](blackbox-evolutionary-vision.md) — north star: live-compatible black-box exchange engine

## Candidate detail files
- [funding-carry-harvester](funding-carry-harvester.md) — W3 detail: hard part is margin/liquidation engineering, not signal
- [cross-sectional-momentum-portfolio](cross-sectional-momentum-portfolio.md) — W5 detail: weekly rank, fees are the killer
- [execution-plan-2026-07](execution-plan-2026-07.md) — 2026-07-04 pivot candidate order (mission file is authoritative)

## GA-era history (archival — superseded by ga-parked + calibrated-negative)
- [ga-architecture-reality](ga-architecture-reality.md) — GA was a parameter jitterer over 7 families, NOT a composition engine
- [daily-meanreversion-goes-positive](daily-meanreversion-goes-positive.md) — RSI MR positive daily, negative 1h; fee-dominated
- [stop-loss-hurts-mean-reversion](stop-loss-hurts-mean-reversion.md) — fixed stops made RSI MR worse on every metric
- [chunk-a-findings](chunk-a-findings.md) — pulse is pair-specific; symmetric-std penalty misfires
- [chunk-c-search-loop](chunk-c-search-loop.md) — GA mechanics + OOS scoring + fragility filter; `coinmon search`
- [chunk-d-graduation-gate](chunk-d-graduation-gate.md) — graduate(): holdout + fragility go/no-go
- [chunk-f-live-forward-feed](chunk-f-live-forward-feed.md) — BarStepper + LiveFeed/ForwardRunner; `coinmon forward`
- [first-live-search-graduation](first-live-search-graduation.md) — 5-seed sweep all NO-GO → added perp short
- [perp-short-capability](perp-short-capability.md) — PerpPortfolio + 3-state engine + direction genes
- [leverage-breaks-fitness-scaling](leverage-breaks-fitness-scaling.md) — OOS fitness rewarded lucky leverage
- [chunk-l-live-validation](chunk-l-live-validation.md) — killed the reckless-leverage attractor
- [direction-gene-overfits-regime](direction-gene-overfits-regime.md) — direction gene overfit the search regime → chunk M
- [n2-parallelism-overhead](n2-parallelism-overhead.md) — multiprocessing only wins at heavy scale; default serial
- [n6-multiseed-sweep-convergence](n6-multiseed-sweep-convergence.md) — 15-trade gate converged to one pair, one regime
- [chunk-o-cross-pair-robustness](chunk-o-cross-pair-robustness.md) — chunk O is a golden/specialist TAGGER, not a gate
- [chunk-p-bounded-combo](chunk-p-bounded-combo.md) — fixed-shape multi-indicator genome family
- [first-live-combo-cross-pair-sweep](first-live-combo-cross-pair-sweep.md) — combo GOs all SPECIALIST; superseded
- [first-golden-structural-edge](first-golden-structural-edge.md) — first GOLDEN refuted by nested holdout
- [edge-certificate-implemented](edge-certificate-implemented.md) — per-trade OOS ledger + `coinmon certify`
- [chunk-v-null-calibration](chunk-v-null-calibration.md) — C4 nulls; `coinmon nullcheck`
- [w1-ratio-momentum-family](w1-ratio-momentum-family.md) — `ratio_momentum` family
- [w4-donchian-breakout-family](w4-donchian-breakout-family.md) — `donchian_breakout` family
- [w3-funding-cashflow](w3-funding-cashflow.md) — funding as per-bar cashflow (`PerpPortfolio.apply_funding`)
- [chunk-y-ensemble-certification](chunk-y-ensemble-certification.md) — `certify_ensemble` pooled ledger
