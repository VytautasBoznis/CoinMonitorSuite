# Alpha Hunt — Plan B (pre-registered fallback probe pack)

*Written 2026-07-03, BEFORE chunk Y has run. This is the answer to "what do we probe if the
main plan finds nothing." Pre-registering it now — before any Y result is known — is the same
discipline as the T0 pack: decision rules frozen before data, so a future negative can't quietly
bend the follow-up toward whatever noise looks best that day. Read alongside
.claude/plans/alpha-hunt.md (chunks T–Y) and docs/evolutionary-strategy-findings-2026-06.md.*

---

## 0. Trigger — when Plan B activates (and when it must NOT)

Plan B activates **only** on the calibrated negative defined in alpha-hunt.md §Y outcome 2:

> Chunk Y completes (expanded universe, all W families, both timeframes, full null calibration)
> with **zero CERTIFIED** strategies/ensembles, AND the nulls explain the results (best real
> candidate's `t_exp` ≤ the pooled null 95th percentile).

That outcome means: *per-pair price-shape rules on daily/4h crypto candles carry no
retail-reachable edge at taker costs.* It does **not** mean "search harder" — it means the
**inputs** were exhausted. Plan B therefore changes inputs only:

1. **new predictor data** (flows/positioning, not price shape),
2. **new event structures** (episodic effects a bar-by-bar family can't express),
3. **the cost side** (maker execution halves the hurdle every family died on).

**Explicitly forbidden responses to the negative** (restating standing discipline):
- growing GA budget (pop/gens/seeds) to chase a result,
- relaxing any certificate threshold or null quantile,
- re-running the same families on more seeds until one passes,
- running these probes early and letting their results tune the CURRENT plan's families
  (that leaks Plan B's alpha into Plan A's multiple-comparisons bill). **Exception: data
  collectors (§2) start immediately** — collection has no statistical cost, and the history
  cannot be backfilled later.

If Y instead ends with a CERTIFIED edge, Plan B stays parked; its collectors keep running
(the data only gains value) and its probes become the *next* hunt after the first edge is
in forward paper.

---

## 1. The probe pack (frozen 2026-07-03)

Same methodology as T0: **fixed parameters, no search, no tuning; scripts in `probes/`
printing PASS/FAIL against the frozen rule; seeded bootstraps; cross-coin consistency as the
multiple-comparisons guard.** A PASS funds a chunk (§3); it never means "trade it." A FAIL
deprioritizes; it does not delete (a probe is one thin sample too). "The 5 majors" = BTC,
ETH, SOL, BNB, XRP (USDT legs, Binance history where deeper). All return measures are net of
the honest round-trip cost model unless stated. **Never adjust a rule after seeing its result.**

### Tier P1 — data already in the DB once chunk T's scrape lands (run first, all cheap)

| id | hypothesis | test (fixed, no search) | frozen decision rule |
|---|---|---|---|
| B1 | post-shock reversal: a ≥2σ down 4h bar overreacts and bounces | per major: shock = 4h log return < −2σ (rolling 90-bar σ, point-in-time); event study of cumulative net return over next 1/3/6 bars, 10k seeded bootstrap 95% CI | PASS if the 3-bar CAR CI excludes 0 positive AND mean CAR > 1× round-trip cost, on ≥3 of 5 majors |
| B2 | volume shock conditions next-bar return (continuation or reversal) | per major, 4h: volume z-score > 2 (rolling 90-bar, point-in-time) split by bar sign; conditional next-bar mean vs unconditional, bootstrap CI on the difference | PASS if either conditional branch's difference-CI excludes 0 with the SAME sign on ≥3 of 5 majors |
| B3 | cross-venue lead-lag at 4h (Binance prints information Bybit follows, or vice versa) | per major: corr(venue-A ret_t, venue-B ret_{t+1}) both directions, bootstrap CI; lag-0 reported for context only (H4 discipline) | PASS if lag-1 CI excludes 0 same sign on ≥3 of 5 majors in EITHER direction |
| B4 | rebalancing premium (variance harvesting) is collectible net of fees | equal-weight basket of 5–10 decorrelated bases; daily and weekly rebalance vs same-basket buy-and-hold, net of fees, full history + rolling 1y windows | PASS if net premium > 0 in ≥70% of rolling 1y windows at EITHER cadence |

*B4 caveat (honest):* the premium is a portfolio overlay, not a per-trade signal — it has no
trade ledger, so the Edge Certificate doesn't apply as-is. A PASS funds a small design note on
certifying overlays (pooled per-rebalance-period returns as the "trades"), not a family.

### Tier P2 — needs a new collector (start collectors NOW — §2; run probes only on trigger)

| id | hypothesis | test (fixed, no search) | frozen decision rule |
|---|---|---|---|
| B5 | open-interest change carries next-bar information (crowding/deleveraging) | per major perp, 1d: rank-IC of ΔOI percentile (rolling 90d, point-in-time) vs next-day return, bootstrap CI; plus event study of OI-crash days (ΔOI < −10%) | PASS if IC CI excludes 0 same sign on ≥3 of 5, OR the OI-crash event CAR CI excludes 0 on ≥3 of 5 |
| B6 | spot–perp basis extremes mean-revert collectibly | per major: basis = perp close / spot close − 1 (same venue, same bar); event study at basis percentile >95 / <5 (rolling 180d): next 1–5d convergence PnL of the fee-paying convergence trade | PASS if convergence net CAR CI excludes 0 positive on ≥3 of 5 majors |
| B7 | positioning ratio is a contrarian signal at extremes | per major: Bybit long/short account ratio percentile (rolling, point-in-time) >90 / <10; conditional next-day mean vs unconditional, bootstrap CI | PASS if difference-CI excludes 0 with the contrarian sign on ≥3 of 5 majors |
| B8 | new listings drift (or fade) tradably in their first weeks | pooled event study across ALL bases' listing dates (both venues, `coinmon markets` has them): CAR days 1–5, 6–20 post-listing vs matched-market benchmark; needs ≥40 events | PASS if either window's CAR CI excludes 0 (any sign — a reliable fade is as tradable as a drift) |

### Tier P3 — the cost side (diagnostic; can run alongside P1)

| id | hypothesis | test | frozen decision rule |
|---|---|---|---|
| B9 | the fee hurdle, not signal absence, killed the families | re-run Y's top-10 by `t_exp` (regardless of verdict) with maker fees + conservative limit-fill (entry limit at prior close; filled only if the bar trades through it; unfilled = skipped trade) | informational, no PASS/FAIL: report per-candidate expectancy delta. If ≥5 of 10 flip expectancy-positive, fund Z3 (honest maker execution model) |
| B10 | 1h bars clear a MAKER round-trip (H3 analogue one level down) | distribution of \|close-to-close\| per 1h bar vs maker round-trip cost on the 5 majors | PASS if median \|move\| ≥ 2× maker round-trip on ≥3 of 5 majors |

*B9/B10 caveat (honest):* every fill model for limit orders is optimistic somewhere (queue
position, adverse selection — you get filled MORE when the move continues against you). A
maker-side "edge" from these probes funds infrastructure work, never a certificate. Adverse
selection must be priced in Z3 before any maker result is believed.

### Tier P4 — external data (only if P1–P3 all fail)

| id | hypothesis | test | frozen decision rule |
|---|---|---|---|
| B11 | stablecoin supply growth is a slow risk-on regime signal | aggregate USDT+USDC market cap (CoinGecko, free), 30d growth percentile vs forward 30d BTC/ETH return, IC with CI; monthly = few independent samples, say so in the report | PASS if IC CI excludes 0 (this is ~70 monthly observations — treat even a PASS as weak) |
| B12 | BTC-dominance rotation times the alt basket | BTC dominance 30d trend (point-in-time) as a switch between BTC and the equal-weight alt basket; vs both static legs, net of switching costs, rolling windows | PASS if the switched portfolio beats BOTH static legs in ≥60% of rolling 1y windows |

**Accounting note:** this pack is itself ~12 hypotheses × ~5 assets. The cross-coin/-window
consistency requirements are the guard (as in T0, where they correctly let 1-of-35 noise fail
H2), and any family built from a PASS still faces the full certificate + all three nulls —
the probes only decide where compute goes, never what is true.

---

## 2. Collectors to start IMMEDIATELY (calendar-time-critical, zero statistical cost)

Exchange APIs serve **limited lookback** for non-candle series; every week not collecting is
history lost forever. These are scraper additions (same pattern as chunk T's `funding_rates`
table + `ingest_funding`), all off-by-default config-gated jobs, landable in one small chunk (Z0):

1. **Open interest** (`open_interest(exchange, symbol, ts, oi)`) — ccxt
   `fetchOpenInterestHistory`, Bybit serves a limited window (verify depth at build time; assume
   months, not years) → feeds B5.
2. **Long/short account ratio** (`positioning(exchange, symbol, ts, ratio)`) — Bybit-specific
   endpoint, shallow history → feeds B7.
3. **Perp candles for the scraped bases** (reuse the existing candle pipeline with the perp
   symbol) → feeds B6 (basis is computed, not fetched — point-in-time by construction).
4. **Listing-date snapshots** — persist `coinmon markets` output (venue, base, listing date)
   monthly → feeds B8 with clean event dates.

Funding-rate history is already collected (chunk T). Candles are deep on both venues — no
urgency there.

---

## 3. Chunk map (funded only by PASSes; letters continue after Y as Z-series)

| chunk | contents | funded by |
|---|---|---|
| **Z0** | the §2 collectors (scraper tables + backfill jobs) | unconditional, start now |
| **Z1** | event-study engine seam: episodic entries (shock/basis/OI events) as a first-class strategy shape — the current bar-by-bar `Strategy` expresses "state," not "episode"; a thin `EventStrategy` wrapper (enter on event, exit after k bars / on condition) makes B1/B5/B6/B7/B8 representable as families under the SAME certificate + nulls | any of B1, B5, B6, B7, B8 |
| **Z2** | flow/positioning features into `BarView.features` via the feature-store seam (OI, ratio, basis join funding_rate) + families consuming them | B5 or B7 |
| **Z3** | honest maker execution model: limit fills with adverse-selection pricing, maker fee tier, unfilled-order accounting; re-certify survivors under it | B9 signal (≥5/10 flip) or B10 |
| **Z4** | external-data regime overlay (stablecoin/dominance) as a modifier gene | B11 or B12 |
| **Z5** | **the pivot decision** — if the ENTIRE pack fails: write the calibrated-negative paper (docs/), ship Phase 2 (scanner/suggestions UI) on the best UNPROVEN candidates as *monitoring* (never live capital), keep W3 carry as the structural-yield component, and re-open the hunt only with a genuinely new input class (order-book/intraday infra = old S8, or paid on-chain data) as a conscious project decision with the user | all of P1–P4 failing |

Priority logic mirrors T0's: fund whatever passes cheapest first (P1 before P2 before P4);
B9/B10 run in parallel since they recycle Y's own artifacts.

## 4. Why these and not more families in the current space

The calibrated negative, if it arrives, will have *already priced* the current space: five
price-shape families, two timeframes, hundreds of pairs, full null correction. Every Plan-B
probe therefore introduces an input the certificate has never seen — positioning (B5, B7),
market structure (B6, B8, B9, B10), cross-venue information (B3), portfolio effects (B4),
macro flows (B11, B12) — or an effect *shape* (episodic events, B1) the bar-state genome
cannot express. Nothing in this pack is "the same idea with different parameters." That is
the one property that makes a second hunt worth its multiple-comparisons bill.
