---
name: w3-carry-first-live-diagnosis
description: "W3 funding-carry — CERTIFIED 2026-07-06, the project's FIRST certified strategy (1 of 3 for the UI gate). The premium is real+robust; smoothed-HOLD design (not percentile-toggle) captures it; carry-appropriate Edge Certificate (per-bar net carry, 41 USDT perps, 1d): CERTIFIED at +2.23%/yr, t+4.08, C4 block-sign-flip null + C6 fee/funding fragility both PASS. ~$10 micro-live now UNLOCKED. Run at 1d, never sub-8h (4h REFUTED)"
metadata:
  node_type: memory
  type: project
  originSessionId: continue-w3-diagnosis
---

First live run of the W3 carry stack ([[funding-carry-harvester]], [[w3-funding-cashflow]],
[[mission-find-edge-ship-ui]] candidate b). Machine: the tooled Windows box (Docker TimescaleDB up,
funding data real — 58 symbols, 2020-03→2026-07, ~256k settlement rows). All numbers below are
in-sample, gross of borrow/basis/slippage-beyond-taker, 1x self-funded CarryPortfolio (no
liquidation risk), taker_fee 0.1%.

**THE PREMIUM IS REAL (this is the headline — first promising signal in the project).**
Continuous-hold (enter the hedge once, apply funding every bar, exit at end — one round-trip fee)
on 29 Bybit USDT perps at **1d**: **mean +2.1%/yr, median +1.6%, 26/29 positive** (BTC +6.8, XRP
+10.2, ETH +5.3). Losers are exactly the high-negative-funding coins (AXS 62% neg-funding bars,
TRX/BNB 42%). Cross-coin robust, not a single-pair fluke.

**THE FAMILY CHURNS IT AWAY.** `FundingCarry` hedges only when the CURRENT funding is >0 AND ranks
≥ entry_pct percentile of a rolling window → it re-hedges on every funding wobble. At 1d/entry_pct=0
that's still ~150 toggles/pair (~30/yr); at 0.2% per 4-leg round-trip that's ~6%/yr in fees, turning
+2% gross into **−1.4%/yr net (only 7/29 positive)**. entry_pct is an ANTI-FEATURE: higher = more
churn = worse on every pair. **At 4h it's catastrophic (−99%, ~3800 trades):** funding settles every
8h so `align_funding` yields an alternating `[rate,0,rate,0,…]` series (51% of 4h bars exactly 0) →
the family un-hedges on every zero bar → churns every single bar → pure fee death. **Carry must be
run at 1d, never sub-8h, until the sparse-funding representation is fixed.**

**THE FIX LANDED (2026-07-06, W3 step 3a — DONE, 403 tests green, ruff clean, verified live).**
`FundingCarry` now gates on the rolling-MEAN funding clearing a `threshold` (params: `window`
20–200, `threshold` 0.0–0.0005; `entry_pct` REMOVED). Verified through the real
`decode()→BacktestEngine` path on 12 USDT perps at 1d (window=30, threshold=0): **mean +5.47%/yr,
median +6.17%, 11/12 positive** — matches the prototype below. STILL 1x unlevered (conservative
floor; 2–3x on the neutral book → ~10–15%/yr but adds perp-leg margin risk to model first).

**The prototype that motivated the fix — smoothed-funding HOLD.** Gate on the rolling-MEAN
funding > 0 (point-in-time) instead of instantaneous funding, so the hedge holds through single-bar
noise and only exits genuine negative-funding regimes. W=30 (1d): **mean +4.9%/yr, median +4.5%,
29/29 positive, only 2–27 trades total over 5 yrs** — BEATS continuous-hold because it dodges the
negative-funding stretches (AXS/TRX/BNB all flip positive) while paying almost no fees. W=90:
+3.2%/yr, 29/29. The signal is "stay hedged while the funding regime is positive," not "toggle on
the funding percentile."

**Two pipeline seams block a clean certify run (both quote-bound to USDC):**
1. `data.funding.attach_funding` returns the frame UNCHANGED unless `pair.quote ==
   settings.quote_currency` — so USDT perps get no funding column unless you run with quote=USDT
   (the train side, [[train-usdt-certify-usdc]]). USDC perps (settings default) DO get funding but
   are the least-crowded/lowest-funding venue.
2. `data.candles.load_candles` treats any non-USDC-quote pair as a RATIO to synthesize → certify's
   `select_eval_pairs` over the 465-pair universe would pick mostly ratios (no funding → 0 carry
   trades), pooling almost nothing. **Carry needs its own eval universe = DIRECT funded perps**, the
   "own evaluation seam" the mission always said carry needs.

**Also: the Edge Certificate's N≥300 / per-trade Wilson may not fit carry** — a hold strategy makes
~5–10 round-trips/pair; the evidence is per-BAR funding accrual across pairs/regimes, not per-trade
win rate. Pooling 29 pairs × ~10 trades ≈ borderline 300; carry likely needs a bar-level / pooled
evaluation rather than the trade-count certificate.

**W3 STEP 3b DONE + VERIFIED LIVE (2026-07-06) — the carry-appropriate Edge Certificate.** Both
seams + the certificate unit are resolved. User's calls this session: evidence unit = **per-bar net
carry return** (not per-trade Wilson — a hold makes ~5–10 round-trips and each "wins" almost by
construction); venue = **USDT perps** (carry has ~no search-overfit surface — 2 structural params —
so the USDT-train/USDC-certify firewall barely applies; USDT is the deep funded venue: 41 perps,
funding to 2020 vs USDC's 17 from 2022). Built in `search/evidence.py`: `pool_carry_bars` (pools the
CarryPortfolio's per-bar equity `pct_change` = funding credit − any rebalance fee, price PnL cancels
on the neutral book; reuses `_iter_segments`, now yielding `pair` too), `build_carry_evidence` +
`CarryEvidence`, `certify_carry` + `CarryCertificate` (same 6-criterion shape as `certify` minus C2
win-rate; C1 = bars≥300 AND perps≥3, C3 = mean/bar>0 & bootstrap-CI>0, C5 = ≥2 regimes positive &
none catastrophic, C4 null / C6 fragility optional→PENDING), `_regime_means`. CLI **`coinmon
certify-carry`** (builds the direct-funded-perp universe itself; run with `COINMON_QUOTE_CURRENCY=
USDT`). 422 tests green (+10), ruff clean.

**LIVE VERDICT (1d, window=30/threshold=0, 41 USDT perps, 22,391 strictly-OOS bars): UNPROVEN, but
every HARD criterion PASSES.** mean **+0.000061/bar, 95% CI [+0.000035, +0.000093]** (excludes 0),
**t +4.08**, ~**+2.23%/yr** (simple), positive bars 51.3%, **regimes 2/2 positive** (+0.000135,
+0.000005 — recent funding has compressed but stays ≥0). C1/C3/C5 PASS; UNPROVEN only because **C4
(shuffled-funding null) + C6 (fragility) are PENDING** — staged next, exactly like chunk U left C4/C6
to V. The OOS-pooled +2.23%/yr is the honest haircut off the +5.47%/yr in-sample (pooled over ALL 41
perps incl. low-funding ones, per-calendar-bar incl. flat bars). **4h = REFUTED** (mean≈0, 30.5%
positive bars, 1/2 regimes): funding sparsity dilutes the per-bar unit sub-8h — the certificate
correctly steers carry to 1d, confirming the diagnosis's "never sub-8h."

**Carry is now the first strategy with a real, OOS, fee-net, significant (t≈4), cross-regime positive
edge measured on its own appropriate certificate.** Micro-live stays GATED on CERTIFIED.

**W3 STEP 3c DONE + LIVE (2026-07-06) — CARRY IS CERTIFIED. First CERTIFIED strategy in the project
(1 of the 3 the UI is gated on).** C4 + C6 built in `search/evidence.py` (both re-pool `pool_carry_bars`
on the SAME OOS pairs/windows under a perturbed funding read — no engine seam, no leakage change) and
wired into `certify-carry` (`--null-draws`/`--fragility-runs`, default 200, 0=skip→PENDING; caches
candles+funding so 400 re-pools hit the DB once/pair; ~3 min):
- **C4 shuffled-funding null = `carry_null_beaten`.** NOT a time-permutation (that keeps the premium,
  only scrambles timing → would wrongly REFUTE an ambient-premium harvester, which carry IS). Instead
  a **block sign-flip surrogate** (`_sign_flipped_funding_reader`): flip the sign of ~√N-length blocks
  of each perp's funding → drives E[funding]→0 (premium DESTROYED) while keeping magnitude + intra-block
  persistence → a premium-free series a real carry edge must beat. Carry-currency analogue of V3's
  signal-destroyed-data null. Did NOT reuse `data/surrogate.py` (that's per-bar-price block-bootstrap;
  carry's signal lives in the funding series, so the surrogate must act there).
- **C6 fragility = `carry_fragility`.** The neutral book's equity is price-INDEPENDENT, so the stock
  `StochasticExecution` slippage harness is ~inert on carry (would rubber-stamp 100% — a dishonest
  pass). Carry's real fragility is COST vs a thin premium, so each run re-pools under an adverse draw:
  taker fee ×U[1,2] AND funding ×U[0.7,1]; read = fraction of runs keeping mean/bar>0; gate ≥95%.
- **LIVE VERDICT (1d, window=30/threshold=0, 41 USDT perps, 22,391 OOS bars): CERTIFIED.** C4 real
  **+0.000061/bar beats null p95 +0.000005 (12×)**; C6 **100% positive** (a 30% funding haircut +
  doubled fees can't flip it — low-turnover held premium). Same headline figures as the 3b UNPROVEN
  run (+2.23%/yr, t+4.08, 2/2 regimes) — 3c only supplied the two pending criteria. `runs/certify_carry_usdt_1d.txt`.
- The fragility gate GENUINELY bit (real adverse perturbations, not the inert slippage harness) and the
  strategy survived — a true pass, not a rubber-stamp. 419 tests green (+5).

**BUT NOT DEPLOYED — [[live-yield-hurdle]] (user gate, 2026-07-06):** certification unlocked live in
principle, but the user requires an expected FORWARD net yield >= 5%/yr or it's negative EV vs an
index fund. Carry's RECENT regime is only ~+0.18%/yr (the full-sample +2.23% is flattered by the
older +4.9%/yr era); even 3x is ~0.5%/yr. So **carry is PARKED as a MONITORED candidate** — it goes
live only if/when the funding premium widens back toward the older-regime level (then ~5%/yr at 1x,
~15%/yr at 3x). Keep hunting winners 2 & 3 (W5/Plan-B) for the UI gate. See
[[funding-carry-harvester]], [[autotrading-rollout]], [[alpha-definition-edge-certificate]].
</content>
