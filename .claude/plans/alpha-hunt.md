# The Alpha Hunt — plan for finding (and certifying) a ≥51% edge

*Written 2026-07-02. Implementation plan for another model/session to follow chunk-by-chunk.
Continues the [[build-roadmap]] letter scheme with chunks T–Y. Read this alongside
docs/evolutionary-strategy-findings-2026-06.md (the nested-holdout refutation) and
docs/lessons-learned.md.*

---

## 0. Why the current setup hasn't found alpha (diagnosis)

The judge is validated — the nested holdout proved the gate rejects garbage and is not a
rubber stamp. What's broken is not the rig; it's that the rig is being asked questions its
inputs cannot answer:

1. **Sample starvation (binding, mathematical).** 5 bases → 15 pairs, ≤1,660 daily bars
   (BNB 676), ONE macro regime. Every graduation verdict rides on 13–20 holdout trades.
   Win-rate standard error at N=20 is ~11pp — the noise floor is 10× the edge being hunted.
   Detecting p > 0.5 at 95% one-sided confidence requires roughly:
   | observed win rate | pooled OOS trades needed |
   |---|---|
   | 51% | ~6,800 |
   | 52% | ~1,700 |
   | 53% | ~750 |
   | 55% | ~270 |
   Nothing in the current pipeline ever pools more than ~20 evaluation trades per verdict.
   **Every "GO → later refuted" cycle to date is this arithmetic playing out.**
2. **Wrong evaluation currency.** The gate scores *equity return on one holdout tail* —
   that measures "bet the right regime," not "per-decision predictive edge." Hence every GO
   was a crash-short on a crash or a bull-tail artifact ([[nested-holdout-refutes-golden]]).
3. **Anchored hypothesis space.** All families are per-pair, price-only indicator rules
   (RSI mean-reversion, EMA cross, ATR channel, and the combo family composed of the same
   ingredients). This is the space that data-mines best and generalizes worst — RSI got
   anchored from one offhand mention and never re-justified. The signal classes with
   documented persistence in crypto (cross-coin relative momentum, funding-rate carry,
   calendar/seasonality effects) are not representable in the genome at all.
4. **Multiple comparisons never priced.** 30 seeds × pop 300 × 80 gens over 15 correlated
   pairs, and no null distribution to compare the best result against. The skeptical
   reviewer's "randomized-strategy benchmark" was never built.

**Consequences (design principles for everything below):**
- Alpha must be measured **per trade, pooled across many pairs × many time windows**, never
  per one holdout equity curve. Pooling is not optional; it is the only way to reach the Ns
  the table demands.
- Every positive claim must beat an **explicit null** (same pipeline, signal destroyed).
- The search must be given **hypothesis classes where edges are documented**, not more
  degrees of freedom inside the RSI valley.
- More data first: more coins, more pairs, a second timeframe. It is the cheapest chunk and
  every other chunk's power multiplies with it.
- **The user has ZERO strategy/indicator preference** ([[no-strategy-preference]]) — the RSI
  emphasis in the project's history was a past model's anchoring error, not a requirement.
  Never favor, defend, or prune a family by name; only the certificate and the nulls decide.

---

## 1. THE DEFINITION — the Edge Certificate ("at least 51%")

A **trade** is one closed round-trip; its **success** = net return after realized costs > 0.
A frozen genome (or ensemble) **holds an Edge Certificate** iff, over its pooled,
strictly-out-of-sample trade ledger (bars never touched by the search that produced it):

| # | criterion | threshold | rationale |
|---|---|---|---|
| C1 | evidence floor | **N ≥ 300 pooled OOS trades** | below this, 51% is indistinguishable from noise |
| C2 | win rate | observed **p̂ ≥ 0.51** AND **Wilson one-sided 95% lower bound > 0.50** | the literal "at least 51%", stated so it can't be luck |
| C3 | expectancy | mean net return/trade > 0 AND **block-bootstrap 95% CI excludes 0** | kills the 62%-win/negative-expectancy MR trap — win rate alone is a vanity metric |
| C4 | beats the null | certificate score > **95th percentile of the null distribution** (chunk V: random genomes + surrogate data + exposure-matched random entries) | prices the multiple-comparisons burden; a data-mined artifact dies here |
| C5 | regime spread | trades span **≥ 2 disjoint time regimes** and expectancy is positive in **≥ 2 of them**, never catastrophic in any | no more single-regime crash-shorts |
| C6 | fragility | existing Monte-Carlo stress stays ≥ 95% positive on the pooled OOS evaluation | unchanged kill-filter |

- **Certificate score** (the scalar compared against nulls, and the sweep's ranking key):
  `t_exp = expectancy / (bootstrap std of expectancy)` — the t-statistic of per-trade
  expectancy. (Wilson bound − 0.5 is reported alongside but t_exp ranks.)
- Verdicts: **CERTIFIED** (all six), **UNPROVEN** (fails only C1 — not enough evidence, the
  honest "keep collecting" state), **REFUTED** (fails any of C2–C6 with N ≥ 300).
- The existing graduation gate stays exactly as-is, demoted to a **cheap pre-filter** inside
  the search loop. The certificate is the *project-level* definition of alpha; nothing gets
  called alpha, forward-tested with intent, or (ever) traded without it.
- Be honest about C2's arithmetic: at N=300 the Wilson bound needs p̂ ≈ 0.55; observed 51%
  only certifies near N ≈ 6,800. That is the point — "51%" is cheap to *observe* and
  expensive to *prove*, and the plan's data/pooling chunks exist to buy the N.

---

## 1.5 T0 — Precursor probe pack (pre-registered; runs BEFORE the chunks)

Cheap, fixed-parameter pulse checks on data already in the DB. Purpose: decide which hunt
chunks to fund first, and kill dead hypotheses before T scales the data. **Probes are the
chunk-A methodology — fixed params, no search, no tuning.** A probe passing means "fund
that chunk," never "trade it"; every probe lives in the thin-sample regime that produced
the refuted golden. **Decision rules below were frozen 2026-07-02 BEFORE any probe ran;
never adjust a rule after seeing its result.** Probe scripts live in `probes/` and print
PASS/FAIL against their frozen rule.

| id | hypothesis | test (fixed, no search) | frozen decision rule |
|---|---|---|---|
| H2 | weekday seasonality exists in USDC legs | per coin: daily log return by UTC weekday, 10k-resample bootstrap 95% CI (seeded) | PASS if some weekday's CI excludes 0 with the SAME sign on ≥3 of 5 coins (cross-coin consistency is the multiple-comparisons guard: 35 cells tested) |
| H4 | BTC leads alts by one day | corr(BTC ret_t, alt ret_{t+1}) for ETH/SOL/BNB/XRP, bootstrap 95% CI; lag-0 corr reported for context only | PASS if lag-1 CI excludes 0 with the same sign on ≥2 of 4 alts |
| H6 | funding carry premium visible on USDC perps | ad-hoc ccxt funding history (BTC, ETH); mean-rate sign bias with CI; daily-aggregated funding vs next-day return IC | PASS if mean funding CI excludes 0 (carry exists) OR IC CI excludes 0 (predictive); either funds W3's plumbing in T |
| H1 | cross-coin relative momentum has a pulse on ratios | `ratio_momentum` family, FIXED lookback=30/skip=1/band=0, `evaluate_fitness` (4 folds, embargo 5) on chunk A's 8 daily series | PASS if median OOS return > 0 on ≥4 of 8 series AND pooled positive-fold share > 50% |
| H3 | 4h bars clear the fee hurdle | scrape 4h for the existing 5 bases; distribution of \|close-to-close\| per 4h bar vs 0.2% round-trip | PASS if median \|move\| ≥ 0.4% (2× round-trip) on ≥3 of 5 coins |
| H5 | pooling reaches the certificate's N floor | fixed RSI 14/30/50 pooled trade count across 15 pairs × 4 folds (needs U1 ledger seam) | informational, no PASS/FAIL — computes the data multiplier T must buy to reach N ≥ 300 |

Mapping: H1→W1, H2→W2, H6→W3, H4→a new lead-lag family (add to W if PASS), H3→X, H5→T sizing.
A FAIL deprioritizes its chunk; it does not delete the idea (a probe is one thin sample too).

### T0 results (run 2026-07-02, against the frozen rules above — scripts in `probes/`)

- **H2 weekday seasonality: FAIL.** 1 significant cell of 35 (BNB Thursday) = exactly the
  chance rate. Observation NOT acted on (post-hoc): all 5 coins' Thursday means were
  negative and 4/5 Monday means positive — sign-consistent but nowhere near the frozen bar.
  → W2 deprioritized to last.
- **H4 BTC→alt lead-lag: FAIL, decisively.** Lag-0 beta is huge (0.64–0.85, everything
  moves same-day) but lag-1 corr is ~−0.03 on all 4 alts, none significant. Daily lead-lag
  is dead in this data. → no lead-lag family; idea closed for free.
- **H6 funding carry: PASS (carry leg only).** BTC/USDC perp: mean +0.0042%/8h,
  CI [+0.0038, +0.0046], 78% of 4,889 settlements positive (≈ +4.6%/yr to the short side);
  ETH: +0.0052%/8h, 79% positive (≈ +5.7%/yr). But IC vs next-day returns ≈ 0 (both CIs
  straddle 0): funding is a COLLECTIBLE PREMIUM, not a timing signal → W3 should be shaped
  as carry/basis capture (e.g. short-perp overlay / long-spot-short-perp), not as an entry
  indicator. Funding data confirmed available for 68 USDC perps → T's funding table funded.
- **H1 ratio momentum: PASS.** Fixed 30/1/0, chunk-A methodology, 8 series: 5/8 positive
  median OOS, pooled positive-fold share 56% (18/32), ~440 pooled trades. Fat right tail
  (means ≫ medians — classic momentum profile: XRP/ETH mean +96% vs median +12%), still
  net-positive after both fee legs with a churny band=0. Caveats: huge fold variance
  (−39%…+382%), 56% of 32 folds is NOT itself significant (SE ≈ 9pp) — a pulse, not proof.
  → **W1 is funded first**, and its ~50–70 trades/series/4y is the evidence-density the
  certificate arithmetic needs (vs RSI-MR's ~15).
- **H3 (4h fee hurdle): NOT RUN YET** — needs a 4h scrape of the existing 5 bases first.
- **H5 (pooling floor): NOT RUN YET** — needs chunk U1's trade-ledger seam. Early hint from
  H1: 8 series × 4 folds already pooled ~440 momentum trades, so N ≥ 300 looks reachable
  even before T expands the universe (for high-trade families; not for MR).

**Net effect on chunk order:** W1 (ratio momentum) is promoted to immediately after U —
possibly before T completes — since it passed on CURRENT data; W3 next (reshaped as carry
capture); W2 last; lead-lag dropped.

## 2. The chunks

Order: **T → U → V → W → X → Y.** T is pure data and unblocks everything; U redefines the
target before more compute is burned; V makes any positive defensible; W widens the
hypothesis space; X multiplies evidence; Y is the payoff run. Q (tree-GP) stays parked until
Y shows the certificate + null machinery hold. One chunk ≈ one session, per
[[session-build-loop]]; user commits ([[user-commits-themselves]]).

### T — Data expansion (prerequisite; mostly config + scraper time)

The single highest-leverage chunk. Goal: **~25–30 bases → 300+ auto-built pairs, two
timeframes, and funding-rate history.**

1. **Discover candidate bases.** Small helper (script or `coinmon markets` subcommand):
   `ccxt.bybit().load_markets()`, filter `spot && active && quote == "USDC"`, rank by
   listing age / recent volume. Target the ~25–30 with the longest history. (Hard
   constraint intact: USDC quote only, never USDT — [[project-direction]].)
2. **Scrape.** Set `COINMON_SYMBOLS` to the chosen `*/USDC` legs and
   `COINMON_TIMEFRAMES='["1d","4h"]'` (keep 1h off for now — volume of writes, and fees
   killed 1h for these families anyway). Backfill from listing (`COINMON_BACKFILL_START`
   already 2020-01-01). The N4 universe auto-builder then yields n + C(n,2) pairs with no
   code change.
3. **Funding-rate history (feeds W3).** New Timescale table `funding_rates(exchange,
   symbol, funding_time, rate)`; adapter method wrapping ccxt `fetchFundingRateHistory`
   for Bybit USDC-settled perps of the scraped bases; scraper backfill+poll job. Data-only,
   no trading implications.
4. **Report.** After backfill: bars-per-pair distribution, listing dates, how many pairs
   clear ≥ 800 daily bars. This tells chunk Y its usable universe.
5. **Cheap immediate win:** run the already-built-but-never-run `coinmon stability`
   (chunk S) on the expanded data — more bases was its stated prerequisite.

*User-gated decision — RESOLVED 2026-07-02 (YES + a stronger split, see
[[train-usdt-certify-usdc]]):* the quote currency is now the **train/test split**. Search/train
ONLY on USDT (Bybit USDT + **Binance USDT 2017+**, a backtest-history-only venue that never
trades — bends the USDT-ban letter for DATA only); keep every **USDC** series pristine and use
it ONLY at the final Edge-Certificate validation (chunk U/Y). So the search never sees the real
tradable instrument until certification. **Chunk U/Y must honor this:** build the training
universe from USDT, reserve USDC for `certify`.

*Code landed 2026-07-02 (Bybit side + venue plumbing):* `coinmon markets` (base discovery,
`rank_spot`), `funding_rates` table + `BybitAdapter.fetch_funding_history` + scraper
`ingest_funding` (config `scrape_funding`, off by default), `coinmon coverage` (per-quote
universe report), `BinanceAdapter` via an extracted `CCXTSpotAdapter` base + one-shot
`coinmon backfill`. Data run + `stability` are the user's step.

Acceptance: `discover_universe` reports ≥ 200 pairs at 1d; 4h series present; funding table
populated for ≥ 10 perps; stability run executed and its read recorded.

### U — Trade ledger + `search/evidence.py` (the certificate, implemented)

1. **Expose the per-trade ledger.** The engine already computes per-trade net PnL and
   hands it to `metrics.summarize(trades=...)`, then discards it. Add to `BacktestResult`
   a `trades: list[TradeRecord]` where `TradeRecord = (entry_time, exit_time, direction,
   net_return_pct)` (net of both fee legs; stop-outs included). Purely additive — metrics,
   fitness, and all 231 tests stay byte-identical.
2. **Evidence pooling.** `search/evidence.py`:
   - `pool_trades(genome, evaluation_spec) -> list[TradeRecord]`: run the frozen genome
     over an evaluation grid = {every pair in a decorrelated evaluation set (reuse chunk
     O's `pick_decorrelated_pairs`)} × {the holdout segments of rolling windows (reuse
     chunk S's `window_bounds`)}, collecting ledgers. **Dev/eval hygiene:** only bars the
     producing search never saw qualify; keep the standing nested-holdout convention (the
     final certificate always includes the most recent untouched tail).
   - `EvidenceReport`: n_trades, win_rate, `wilson_lower(p̂, n, α=0.05)`, expectancy,
     bootstrap CI (moving-block bootstrap over the *time-ordered* pooled ledger, block
     length ≈ √N, ≥ 5,000 resamples — trades are cross-pair correlated, so blocks must be
     time-blocks, not iid draws), per-window expectancy signs (feeds C5), `t_exp`.
   - `certify(report, null_dist | None) -> EdgeCertificate` with verdict
     CERTIFIED / UNPROVEN / REFUTED and per-criterion pass/fail reasons (mirror
     `GraduationReport`'s explicit-reasons style).
3. **CLI:** `coinmon certify` (takes a genome spec or the winner file of a search/sweep
   run) printing the full report; `coinmon sweep` gains `--certify` to rank GO winners by
   certificate score instead of raw holdout return.
4. **Tests:** Wilson bound against known values; bootstrap CI sanity (synthetic ledgers
   with known edge); a synthetic 55%-win genome certifies at N=300 while a 50% one is
   UNPROVEN/REFUTED; dev/eval leakage guard (searched bars never in the pool).

Acceptance: certifying the refuted BNB/ETH RSI(2) golden genome on today's data yields
REFUTED or UNPROVEN — the certificate must agree with the nested holdout on the known case.

### V — Null-model calibration (`search/nullmodel.py`)

Three nulls, cheapest first. Each produces a distribution of certificate scores; C4
compares against their pooled 95th percentile.

1. **Random-genome null.** Sample M (≥ 200) genomes uniformly (`random_genome`, no
   evolution), push each through the SAME evaluation (gate pre-filter + evidence pooling),
   record the BEST score. Repeat over seeds → distribution of "best of M random tries."
   This is what luck alone buys from the genome space.
2. **Exposure-matched random-entry null (per candidate).** Given a candidate's OOS ledger:
   1,000 draws of {same number of trades, same holding-duration distribution, same
   direction mix, random entry times} on the SAME evaluation series. Candidate expectancy
   must sit ≥ 95th percentile. This kills "profitable by being flat through the bleed /
   long the bull tail" — beta dressed as alpha, the failure mode behind every prior GO.
   **DONE 2026-07-02:** `nullmodel.random_entry_null` + `null_from_distribution` (direct
   percentile, no best-of-M) + `_synthetic_return` (replays each matched trade through the
   genome's OWN `decode_portfolio`, so leverage/fees/liquidation match the engine exactly);
   `evidence.EvalSegment`/`pool_segments` extract per-segment prices + trade durations via a
   shared `_iter_segments` (pool_trades byte-unchanged). CLI `nullcheck --mode matched
   [--resamples]`. 299 tests green (+10), ruff clean. Not yet run live.
3. **Surrogate-data null (dearest, run last).** Stationary block bootstrap of each USDC
   leg's log returns (block length ~20 bars), resampling time-blocks JOINTLY across all
   legs so cross-pair correlation structure survives while temporal signal dies; rebuild
   ratios from surrogate legs. Re-run the FULL search (small config: e.g. 10 seeds ×
   pop 100 × 30 gens) on ≥ 20 surrogate universes → distribution of best certificate
   scores on data known to contain nothing. The real search's best must exceed the 95th
   percentile. This is the White's-Reality-Check analogue and the definitive answer to
   "is 51% real or mined."

CLI: `coinmon nullcheck --mode random|matched|surrogate`. N2 multiprocessing finally earns
its keep here (embarrassingly parallel). Tests: planted-edge surrogate sanity (a synthetic
series WITH a real injected edge must beat its own surrogate null; pure noise must not).

Acceptance: null distributions persisted (JSON) and consumed by `certify` as C4.

### W — Escape the RSI valley: new signal classes as ordinary FAMILIES

Each is a normal `genome.FAMILIES` entry (same registration seam chunk P used), so GA /
gate / certificate / nulls all apply unchanged. Keep the old families in — the certificate
and nulls decide, not curation. Sub-chunks are independent; land in this order:

1. **W1 — `ratio_momentum` (cross-coin relative strength; the documented one).**
   Time-series momentum ON a ratio pair *is* relative momentum between two coins — the one
   effect with real academic persistence in crypto — and it fits the single-series engine
   as-is. Signal: k-bar rate of change with a skip-recent gene and a cost-aware band:
   long when `roc(close, lookback, skip) > band`, flat otherwise (adaptive wrapper
   provides the short side). Params: `lookback` ParamSpec(5, 120, int), `skip`
   ParamSpec(0, 10, int), `band` ParamSpec(0.0, 0.10). ~40 lines + tests, mirrors
   `rsi_meanreversion.py` structure.
   **DONE 2026-07-02:** `strategies/ratio_momentum.RatioMomentum` (exact probe-H1 signal,
   bounded deque = O(1)/bar) + `genome.FAMILIES["ratio_momentum"]`. Registration-only wiring —
   GA/decode/fitness/graduation/cross-pair/certificate/null all consume it unchanged (no GA or
   engine edits). 289 tests green (+15), ruff clean. Family makes cross-coin momentum REACHABLE;
   alpha still unproven pending a live search + certify.
2. **W2 — calendar/seasonality gene (modifier, like `stop_pct`).** A `day_mask: int`
   gene (7-bit weekday mask; bit set = trading allowed, position forced flat otherwise;
   `None`/all-ones = off). Implemented as a wrapper strategy like `RegimeAdaptive`.
   Crypto weekend/weekday effects are documented and orthogonal to price-shape families.
   Cheap; also meaningful at 4h (hour-bucket mask variant).
3. **W3 — `funding_carry` (needs T's funding table).** For USDC perp pairs only: position
   sized against the crowded side when the funding-rate percentile (rolling, point-in-time)
   is extreme; collects the documented carry premium. Requires threading a second
   point-in-time series into `BarView.features` — the feature-store seam
   ([[feature-store-seam]]) exists for exactly this. Largest W item; do last.
4. **W4 — `donchian_breakout`.** N-bar high/low channel breakout with ATR-scaled exit —
   mechanically distinct from EMA cross (stop-and-reverse channel vs moving-average state).
   Cheap (StreamingATR exists).
5. **W5 (design-only for now) — true cross-sectional top-k rotation.** Rank ALL bases each
   rebalance, hold the strongest k. Needs a multi-instrument engine seam — write the design
   note, build only if W1 certifies (W1 is its two-asset special case and the cheap test of
   the same hypothesis).

Acceptance per sub-chunk: family registered + unit tests (signal semantics, no-lookahead,
GA reaches it) + one smoke search where the family is sampled.

### X — 4h evidence multiplication

With T's 4h data: run the same searches at `--timeframe 4h`. 6× the bars per regime and
several × the trades — C1's N floor becomes reachable per-genome, not only pooled. Fees are
the killer at higher frequency, but that is priced honestly: the ledger is net-of-cost, so
C3 simply refuses churny genomes. Work: verify fold/embargo/holdout geometry at 4h bar
counts, one config default per timeframe, nothing structural. Run W1/W2/W4 there first
(momentum families historically live at 4h–1d; MR dies of fees — let the certificate say so).

### Y — The certified sweep (the payoff run) + ensemble

1. **Big sweep:** expanded universe (T), all families (W), both timeframes (X), heavy
   config (N2 parallel: ~20+ seeds, pop ≥ 300, ≥ 80 gens), gate as pre-filter, certificate
   ranking, full null calibration (V). Also re-run `coinmon stability` as the rolling
   diagnostic.
2. **Ensemble evaluation:** take the top-k decorrelated certified (or near-certified)
   genomes (correlation on OOS *daily returns*, not equity), equal-weight their pooled
   ledger, certify THE ENSEMBLE as its own unit. Small edges become tradable only
   aggregated — the portfolio is the deployment unit chunk R will allocate.
3. **Two honest outcomes:**
   - **≥1 CERTIFIED strategy/ensemble** → alpha, as defined, exists → proceed to chunk G
     (forward paper suggestions) with the certificate as the entry ticket, and revisit Q
     (tree-GP) now that the judge demonstrably scales.
   - **Everything UNPROVEN/REFUTED with the nulls explaining all results** → the calibrated
     negative: price-shape rules on daily/4h crypto carry no retail-reachable edge at these
     costs. That conclusion is *publishable-grade honest* and redirects the project (W3
     carry / W5 cross-sectional / alternative data) instead of burning more compute in the
     same valley.

---

## 3. The search-space menu (the options, strategy-blind)

Candidate hypothesis classes, each expressible as one or more FAMILIES (or modifier genes)
in the existing registry. None is favored ([[no-strategy-preference]]); prior-evidence
notes are about where to spend compute first, and the certificate + nulls decide what
survives. Dimensionality matters: it is the overfit surface the nulls must price.

| id | space | genes (≈dims) | prior evidence | status / cost |
|---|---|---|---|---|
| S1 | per-pair price-shape rules (RSI-MR, EMA cross, ATR channel, combo) | 2–9 + shared 5 | weak; classic data-mining valley — one refuted golden already | built; keep in pool, fund nothing new |
| S2 | cross-coin relative momentum (time-series momentum on ratio pairs) | 3 + shared | strongest documented crypto effect (momentum/relative strength) | W1, ~40 lines; probe H1 |
| S3 | cross-sectional top-k rotation over the whole universe | 3–4, but multi-instrument engine | same literature as S2, purer expression; many decisions/bar → N floor reachable structurally | W5 design-only, gated on S2 certifying |
| S4 | calendar/seasonality (weekday/hour masks) | 1 mask gene (modifier, composes with any family) | documented but decaying; cheap | W2; probe H2 |
| S5 | funding-rate carry / basis (USDC perps) | 2–3 + data plumbing | structural premium (payment for taking the crowded side's risk) — least like curve-fitting of all options | W3, needs T funding table; probe H6 |
| S6 | lead-lag spillover (BTC move → next-bar alt/ratio position) | 2–3 (lag, threshold) | documented in lower-liquidity eras; may have decayed | new family if probe H4 passes |
| S7 | volatility-regime overlays (vol filter / vol-scaled sizing) | 1–2 modifier genes | vol clustering is the most robust stylized fact; as a FILTER not a signal | cheap add-on after any family certifies |
| S8 | intraday microstructure (<1h) | many | real but fee/latency-killed at retail taker; needs maker infra | out of scope for now |

## 4. Is the GA the right tool? (verdict: possible tool, currently overkill — keep, demote, re-audit)

Honest assessment, 2026-07-02:

- **Current search spaces don't need it.** Every family is 2–9 params plus ~5 shared genes.
  At ≤ ~10 dimensions, seeded random search + local refinement is known to be competitive
  with evolutionary methods; the GA's population machinery is buying little over the
  random-genome baseline *at this dimensionality*. The refuted golden proves the corollary:
  the GA optimizes whatever the fitness rewards very well — the binding constraint was
  never optimizer power, it was evaluation honesty and representability.
- **It is not harmful either, and it is built, deterministic, memoized, parallel, and
  tested.** Ripping it out buys nothing. The danger of ANY strong optimizer (GA included)
  is selection intensity = overfitting pressure; that is priced by the certificate + nulls,
  not by weakening the optimizer.
- **Where it becomes the right tool:** combinatorial/structured spaces — the combo family
  (mixed discrete×continuous), S3's joint pair-set selection, and above all tree-GP (Q),
  which is *only* searchable evolutionarily. The GA is infrastructure ahead of its need,
  not waste.
- **Operational consequences:** (1) V1's random-genome null doubles as a permanent
  "is the GA beating random search?" audit — if evolved winners don't beat best-of-M-random
  under equal evaluation budget, run random search and save the compute; (2) never grow GA
  budget (pop/gens) to chase a result — grow DATA and EVIDENCE instead; optimizer budget
  only rises with representation size (P/Q/W5).

## 5. Standing discipline (unchanged, restated)

- The search overfits; only the certificate is trusted ([[search-overfits-not-strategy]]).
- Fragility remains a kill-filter, never a badge.
- No real capital anywhere near this until a certificate AND forward paper evidence exist;
  chunk I safety gating unchanged.
- Never tune anything to pass the certificate or the nulls — they are the exam, not the
  training set. If a change is motivated by "it would certify then," stop.
- User commits themselves; deliver commit messages ([[user-commits-themselves]]).
