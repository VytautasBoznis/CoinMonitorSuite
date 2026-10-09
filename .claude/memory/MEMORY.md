# CoinMonitorSuite Project Memory

This file indexes all memory files. One line per file; detail lives in each topic file.

## Read first — mission & standing directives
- [mission-find-edge-ship-ui](mission-find-edge-ship-ui.md) — **THE MISSION: find ≥3 winner strategies → build UI → confirmed/auto trading. UI gated on ≥3 winners; Z0 collectors start immediately; ~$10 micro-live authorized for the first promising strategy**
- [live-yield-hurdle](live-yield-hurdle.md) — **USER GATE: certified ≠ deploy. Real capital needs expected FORWARD net yield ≥5%/yr (weight recent regime). Carry certified but recent ~0.18%/yr → PARKED until premium widens**
- [riskier-strategies-allowed](riskier-strategies-allowed.md) — **DIRECTIVE 2026-07-18: riskier strategies allowed — relaxes DRAWDOWN/variance ONLY; ≥5%/yr floor + honesty NOT relaxed. Plus ANOMALY-FOCUS refinement: hunt anomalies with a path-to-hurdle bar, fastest-first (scanner→dislocations→combine)**
- [anomaly-hourofday-lead](anomaly-hourofday-lead.md) — **FIRST path-to-hurdle ANOMALY (2026-07-18): anomaly scanner (`probes/anomaly_scan.py`) found the 21:00-23:00 UTC US-session-close effect. B20 PASSED out-of-sample — 5/5 majors net-maker positive (median +16%/yr), out-of-ASSET significant (BNB t=6.0), coherent plateau. BUT edge exists ONLY at maker fees, needs 52-90% maker fills → maker-execution bet, needs live-paper validation. Cross-sectional factors all sub-threshold. First real candidate; still 0 certified**
- [fuck-it-we-ball-mode](fuck-it-we-ball-mode.md) — **DIRECTIVE 2026-07-31: owner bored with the grind — EXTREME strategies authorized ("fuck it we ball") for ideas Mr Fable (Anthropic's Fable) has authorized. Exotic venues/plumbing/collectors now in scope; ≥5%/yr floor + honesty still stand**
- [fable-batch-10-probe-queue](fable-batch-10-probe-queue.md) — **THE ACTIVE QUEUE: Fable's 10 ideas ranked by EV/probe-hour, each with pre-registered PASS/KILL. Today: 1 tail-gated carry, 2 BNB Launchpool hedge, 3 quarterly basis + delisted-symbol ETL in parallel**
- [bybit-dropped-no-eu-leverage](bybit-dropped-no-eu-leverage.md) — **DECISION 2026-10-09: Bybit DROPPED for execution — global rejected owner (EU), Bybit EU is spot-only (0 perps verified). No leverage = no Bybit. REPLACEMENT LOCKED: HYPERLIQUID (agent key must be proven unable to withdraw on testnet before money)**
- [bybit-only-leverage-doctrine](bybit-only-leverage-doctrine.md) — **(VENUE SUPERSEDED by bybit-dropped-no-eu-leverage; leverage-class caps still reusable)** Bybit-only = EXECUTION constraint only (Binance data stays); 20x caps: 5-8x hedged books in UTA cross-margin, 2-3x HARD on ladders, never naked directional (liq ~4.5% away). Flags the MiCA/USDC-only conflict that may gut the tradable universe for ideas 1/4/6/10**
- [cursed-100-eur-live-ladder](cursed-100-eur-live-ladder.md) — **the cursed 100 EUR goes LIVE this week into idea-8 liquidation-cascade resting bid ladders (2-4% under mid, BTC/ETH/SOL perps, isolated margin); micro-live data-gathering, not a deployment**
- [live-bot-dashboard-plan](live-bot-dashboard-plan.md) — **DIRECTIVE 2026-10-09: UI gate LIFTED for a live-bot inspection dashboard (bot + UI together). No manual trade button; PANIC/DRAIN stop modes; UI writes only pause/kill. BOT CORE BUILT 2026-10-09 on Hyperliquid (fake-venue tests only; testnet run + agent-can't-withdraw proof owed before money); F11 spec still missing**
- [no-strategy-preference](no-strategy-preference.md) — user has ZERO strategy/indicator preference; only "certified/winnable" matters; never favor a family from a mention
- [no-more-rsi-ema-permutations](no-more-rsi-ema-permutations.md) — price-transform indicator strategies exhausted (0 CERTIFIED); never refocus; legacy families are baseline/control only
- [ga-parked](ga-parked.md) — **GA HARD-BANNED: never run `coinmon sweep`/`search` or re-run old sweeps for any reason; run GA-free on persisted artifacts or surface the conflict**
- [honest-status-reporting](honest-status-reporting.md) — never claim work done without artifact evidence; surface scope downgrades loudly (burned by ~2 wks of false sweep-progress claims)
- [no-multi-hour-data-loads](no-multi-hour-data-loads.md) — **USER RULE 2026-10-08: no multi-hour backfills on the test machine; skip tests that need them; estimate load time before launching**
- [user-commits-themselves](user-commits-themselves.md) — never run git commit; hand over a commit message and stop
- [session-build-loop](session-build-loop.md) — session shape: read memory → next roadmap chunk → ask blockers → deliver a commit message

## Current status & active leads (2026-07: still 0 deployable winners)
- [f8-cascade-ladder-result](f8-cascade-ladder-result.md) — **F8 PASSED 4/4 on 1m SPOT (+0.54%/event) AND PERP (2026-10-08: +0.51%/event, N=2261, 6/6 yrs). Perp recent-24mo +6.99%/yr acct on touch-fills, but 0.1% trade-through → +5.22% CI touches zero; >2% wicks lose worse on perp; 20x liquidates 17% of fills. Not deployable; license (collector + micro-live) survives. Collector now RUNNING; NEXT (proposed): F8 rerun on Bybit-native 1m klines to settle the venue half of queue risk**
- [f9-weekend-vrp-killed](f9-weekend-vrp-killed.md) — **F9 weekend VRP KILLED 2026-10-08 on real Deribit Monday-expiry prints (BTC+ETH); DVOL proxy pass was the calendar effect; long side = snooped shock lottery**
- [f7-f3-killed](f7-f3-killed.md) — **F7 clock scalp KILLED (−12bp/event) + F3 quarterly basis KILLED (+3.94%/yr incl. flat, nothing since 2025-03), 2026-10-08. Every structural premium is 2021-22-fat, recent-dead**
- [f6-new-listing-funding-killed](f6-new-listing-funding-killed.md) — **F6 new-listing funding KILLED 2026-10-08 both venues (hit <60%); +1.5%/listing mean is a tail; hedge = scarce borrow; cross-venue hedge doctrine-blocked**
- [f5-polymarket-favorites-killed](f5-polymarket-favorites-killed.md) — **F5 Polymarket favorites KILLED 2026-10-08 (gap −1.53pp, overpriced if anything) + Polymarket API gotchas**
- [bybit-liquidation-collector](bybit-liquidation-collector.md) — **allLiquidation collector RUNNING since 2026-10-08, with a ~22h OUTAGE 10-08 19:24→10-09 17:26 UTC (box slept; timescaledb has no restart policy) (local docker `liquidations` → local Timescale; stitch into central DB later). Verified: side 'Buy' = LONG liquidated (forced selling); one bad topic poisons a subscribe batch; read prints only inside liquidation_coverage spans**
- [f1-tail-gated-carry-result](f1-tail-gated-carry-result.md) — **F1 PASSED 5/5 (2026-07-31): tail-gated carry +18.89%/yr on deployed vs +3.10% always-on. One-account +8.75%/yr full-sample but only +2.47%/yr recent-24mo → still misses the hurdle. KEY: harder gates raise deployed-yield to +103%/yr but cut account yield → use as capital-light OVERLAY, not standalone**
- [w3-carry-first-live-diagnosis](w3-carry-first-live-diagnosis.md) — **W3 carry CERTIFIED (project's FIRST cert, 1 of 3): +2.23%/yr t+4.08, 22391 OOS bars, 2/2 regimes, C4 null + C6 fragility pass. `coinmon certify-carry`. But parked under the yield hurdle. 4h REFUTED**
- [b13-low-vol-fresh-lead](b13-low-vol-fresh-lead.md) — **LOW-VOL LEAD CLOSED (B14d decomp 2026-07-18): long low-vol leg +12.9%/yr still loses to BTC-hold; short high-vol leg survivorship-suspect, pays off only in 2022 crash. DB is pure-survivor (0 delistings). Closed**
- [session-2026-07-18-tsmom-oi](session-2026-07-18-tsmom-oi.md) — **2026-07-18: B17 TSMOM/CTA portfolio REFUTED (Sharpe 0.24). Built first OI collector — 66,417 daily OI points (5yr, 41 perps) in new open_interest table. B18 OI-crowding FAIL (IC=-0.03 weak reversal), B19 OI-trend-filter FAIL worse. P2-OI tested-negative**
- [b16-funding-signal-refuted](b16-funding-signal-refuted.md) — B16 cross-sectional funding-crowding REFUTED (6/12 pos, median -0.23%/yr, win ~coin-flip)
- [certified-sweep-calibrated-negative](certified-sweep-calibrated-negative.md) — chunk Y payoff sweep: 0 CERTIFIED, every t_exp negative; price-shape valley empty → redirect to carry/W5/Plan B
- [xsectional-momentum-first-run](xsectional-momentum-first-run.md) — W5 X-sectional momentum NOT a winner: short leg beats beta but no certifiable per-position edge (best-of-162 REFUTED)

## Plan B (new inputs) & Plan C
- [plan-b-fallback-probes](plan-b-fallback-probes.md) — Plan B: probe NEW INPUTS (B1–B12: OI/positioning/basis/events/maker-costs); Z0 collectors start immediately (lookback finite)
- [plan-b-p1-results](plan-b-p1-results.md) — P1 (B1–B4) all FAIL: post-shock reversal, volume shock, cross-venue lead-lag, rebalancing-premium near-miss. Candle-shape signals exhausted
- [plan-b-p3-results](plan-b-p3-results.md) — P3 cost-side: B10 maker-hurdle FAIL; B9 maker limit-fill infra built (`MakerLimitExecution`) but runner deferred. Fund infra, never a certificate
- [order-flow-direction](order-flow-direction.md) — taker volume delta / OI / long-short ratio candidates; h7-style probe before integration; L2 imbalance rejected
- [order-flow-probe-h7-refuted](order-flow-probe-h7-refuted.md) — H7 taker-flow/CVD REFUTED (contemp corr +0.4 but next-bar IC≈0); OI + liq-fade collector-gated
- [liquidation-cascade-fade](liquidation-cascade-fade.md) — event-driven post-cascade reversal; record Bybit liquidations early (websocket-only, shallow history); pool across symbols
- [onchain-stablecoin-netflow](onchain-stablecoin-netflow.md) — stablecoin exchange netflow liquidity signal; lowest priority, paid-data burden
- [plan-c-onchain-ideation](plan-c-onchain-ideation.md) — IDEATION only, parked behind Plan B: DEX insider-accumulation-before-listing; needs fat-tail cert + exit-depth gate; own-DEX rejected

## Methodology & rig
- [alpha-definition-edge-certificate](alpha-definition-edge-certificate.md) — THE alpha definition: pooled-OOS-ledger Edge Certificate (N≥300, Wilson>0.50, expectancy CI>0, beats nulls, ≥2 regimes)
- [portfolio-search-protocol](portfolio-search-protocol.md) — post-GA winner-finding: no pair param, exhaustive small grid ALL recorded w/ multiple-testing deflation, portfolio cert vs EW-universe
- [strategy-lab-model](strategy-lab-model.md) — the evaluator is the product: one-command gauntlet; candidates from research/grids w/ economic rationale; chunk vs Plan namespace decoder
- [train-usdt-certify-usdc](train-usdt-certify-usdc.md) — quote currency IS the train/test split: search on USDT only, USDC pristine for final Edge-Certificate; Binance backtest-history-only
- [fragility-stress-test](fragility-stress-test.md) — Monte Carlo latency/slippage stress test as a kill-filter for thin-margin strategies before live
- [autotrading-rollout](autotrading-rollout.md) — execution modes: suggest-only → auto-on-confirm (certified) → capped full-auto; latency tolerance decides
- [search-overfits-not-strategy](search-overfits-not-strategy.md) — the param SEARCH overfits (−23% OOS) while fixed params survive (+12%); fitness must be OOS/walk-forward w/ penalties
- [nested-holdout-refutes-golden](nested-holdout-refutes-golden.md) — strict nested holdout REFUTES the "golden" edge; 'passed gate' ≠ 'persistent edge'; gate is defensive not alpha
- [regime-adaptive-multiseed-sweep](regime-adaptive-multiseed-sweep.md) — the GATE is a validated trustworthy judge, but durable ALPHA unproven (every GO is a thin-trade crash-short with luck-variance)
- [walk-forward-stability-harness](walk-forward-stability-harness.md) — chunk S `coinmon stability`: rolling re-search + selection-agreement + forward-persistence; diagnostic only
- [first-stability-run-expanded-universe](first-stability-run-expanded-universe.md) — first stability run: clean calibrated NEGATIVE (winners hop, persistence 0/2, trade-starved); gate held

## Environment, data & infra
- [project-direction](project-direction.md) — Python/Bybit greenfield, trade-coins-efficiently, phased backtest→suggestions→automation
- [backtester-reads-timescaledb](backtester-reads-timescaledb.md) — backtester loads candles from TimescaleDB (`db.read_candles`), not Parquet; store.py/fetch-data retired
- [data-package-gitignored](data-package-gitignored.md) — REPO BUG: broad `data/` .gitignore ignores `src/coinmon/data/` package; new data/ files need `-f` or anchored `/data/` rule
- [deployment-target-k8s](deployment-target-k8s.md) — runs in k8s; every component ships as a Docker image; config via env/ConfigMaps
- [user-infra-ui-plans](user-infra-ui-plans.md) — user-owned: k8s/build pipeline for collectors, centralized DB + stitch-CLI; keep new tables merge-friendly (natural keys)
- [ui-roadmap](ui-roadmap.md) — three UI tiers gated on data existing; research UI first (needs TradeRecord exit_reason field), then forward-paper, then product UI
- [machines-and-tooling](machines-and-tooling.md) — user works on multiple machines; verify the stack is runnable before promising runs
- [feature-store-seam](feature-store-seam.md) — BarView point-in-time feature-snapshot contract; post-scraper indicator engine deferred (cache not contract)
- [build-roadmap](build-roadmap.md) — the chunked plan to finish the project; source of truth for what's next
- [prototype-reference](prototype-reference.md) — the .NET bachelor's prototype in C:\Dev\CoinMonitor; patterns to reuse vs gaps
- [user-quant-background](user-quant-background.md) — user has limited quant math; relies on the eval rig + search, not hand-derived strategies
- [blackbox-evolutionary-vision](blackbox-evolutionary-vision.md) — north star: engine = live-compatible black-box exchange; sequential non-atomic legs; GA was the long-term alpha path

## Candidate detail files
- [funding-carry-harvester](funding-carry-harvester.md) — W3 detail: delta-neutral funding capture; hard part is margin/liquidation risk engineering at 1-2x, not signal
- [cross-sectional-momentum-portfolio](cross-sectional-momentum-portfolio.md) — W5 detail: rank USDT universe weekly, hold top slice; fees are the main killer
- [execution-plan-2026-07](execution-plan-2026-07.md) — the 2026-07-04 pivot candidate order (momentum→carry→order-flow→liq-fade→on-chain); mission file holds authoritative order

## GA-era history (archival — superseded by ga-parked + calibrated-negative)
- [ga-architecture-reality](ga-architecture-reality.md) — GA was a parameter jitterer over 7 hardcoded families, NOT a composition engine; never misdescribe it
- [daily-meanreversion-goes-positive](daily-meanreversion-goes-positive.md) — RSI MR positive on ETH/BTC daily (+12% OOS) vs −6% 1h; fee-domination; downtrend-flattered
- [stop-loss-hurts-mean-reversion](stop-loss-hurts-mean-reversion.md) — fixed stop-loss made RSI MR worse on every metric (stops suit trend, not MR)
- [chunk-a-findings](chunk-a-findings.md) — pulse is pair-specific; pair must be a gene; symmetric-std fitness penalty wrongly rejects all-folds-positive genomes
- [chunk-c-search-loop](chunk-c-search-loop.md) — chunk C GA mechanics (search/ga.py) + OOS-scoring runner + fragility post-filter; `coinmon search`
- [chunk-d-graduation-gate](chunk-d-graduation-gate.md) — graduate() runs winner on never-searched holdout + fragility → hard go/no-go; `search --holdout`
- [chunk-f-live-forward-feed](chunk-f-live-forward-feed.md) — shared BarStepper + coinmon/live (LiveFeed, ForwardRunner); forward replay == backtest; `coinmon forward`
- [first-live-search-graduation](first-live-search-graduation.md) — 5-seed sweep all NO-GO; gate absolute-return rule is regime-dependent; RESOLVED → add perp short
- [perp-short-capability](perp-short-capability.md) — added leveraged perp short (PerpPortfolio + 3-state engine + direction genes) to fix downtrend NO-GO
- [leverage-breaks-fitness-scaling](leverage-breaks-fitness-scaling.md) — OOS fitness mis-scaled for leverage (rewards lucky leveraged folds); search pulled toward reckless leverage
- [chunk-l-live-validation](chunk-l-live-validation.md) — chunk L killed the reckless-leverage attractor; gate IS passable (BNB/ETH long GO +8.5%)
- [direction-gene-overfits-regime](direction-gene-overfits-regime.md) — free direction gene fit to search span but blind to holdout regime = binding cause of NO-GOs; RESOLVED → chunk-M regime-adaptive
- [n2-parallelism-overhead](n2-parallelism-overhead.md) — N2 multiprocessing bit-identical to serial, only wins at heavy scale; default stays serial
- [n6-multiseed-sweep-convergence](n6-multiseed-sweep-convergence.md) — 15-trade gate collapsed the lottery to one convergent pair (BTC/USDC ema adaptive), still one regime
- [chunk-o-cross-pair-robustness](chunk-o-cross-pair-robustness.md) — chunk O is a TAGGER (golden/specialist), not a kill gate; re-graduates a GO on K-of-N decorrelated peers
- [chunk-p-bounded-combo](chunk-p-bounded-combo.md) — chunk P: fixed-shape multi-indicator genome (N indicators + AND/OR) as a normal family; GP half-step before tree-GP
- [first-live-combo-cross-pair-sweep](first-live-combo-cross-pair-sweep.md) — first P+O sweep: combo competitive, all GOs SPECIALIST (0 golden); superseded
- [first-golden-structural-edge](first-golden-structural-edge.md) — 30-seed grind FIRST GOLDEN (rsi_mr BNB/ETH 2x); REFUTED by nested holdout as regime artifact
- [edge-certificate-implemented](edge-certificate-implemented.md) — chunk U: per-trade OOS ledger + search/evidence.py (Wilson/bootstrap/regime) + `coinmon certify`
- [chunk-v-null-calibration](chunk-v-null-calibration.md) — chunk V (cert C4): V1 random-genome + V2 exposure-matched-entry + V3 surrogate-data nulls; `coinmon nullcheck`
- [w1-ratio-momentum-family](w1-ratio-momentum-family.md) — chunk W1 `ratio_momentum` family (registration-only; pipeline consumes unchanged)
- [w4-donchian-breakout-family](w4-donchian-breakout-family.md) — chunk W4 `donchian_breakout` family (channel + ATR trail); 5th family shifted GA RNG → test budget fix
- [w3-funding-cashflow](w3-funding-cashflow.md) — chunk W3 step 1: perp funding as honest per-bar cashflow (`PerpPortfolio.apply_funding`); step 2 = funding_carry family
- [chunk-y-ensemble-certification](chunk-y-ensemble-certification.md) — chunk Y `certify_ensemble`: pool top-k decorrelated portfolio into one ledger + certify as its own unit
