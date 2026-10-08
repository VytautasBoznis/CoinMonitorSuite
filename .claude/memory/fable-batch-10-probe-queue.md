---
name: fable-batch-10-probe-queue
description: "The authorized work queue (2026-07-31): Mr Fable's 10 extreme-strategy ideas ranked by EV per hour of probe work, each with a pre-registered PASS/KILL probe block, plus the build order."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4520e228-25b0-4c00-a3cd-6a323fb7630d
  modified: 2026-10-08T19:15:53.747Z
---

Delivered by the user 2026-07-31 as the authorized batch under [[fuck-it-we-ball-mode]]. Ranked by EV
per hour of probe work. Probe blocks are meant to be pasted into `probes/` as pre-registered docstrings.
Prompt that produced it: the "cursed 100 EUR" framing — user will burn 100 EUR on a sketchy site if no
idea is picked, so one idea must take live money ([[cursed-100-eur-live-ladder]]).

**1. Tail-gated funding carry** — HIGHEST confidence to certify. Delta-neutral long spot / short perp,
entered only when trailing-3 funding prints annualize >=30%, exit <10%. The certified [[w3-carry-first-live-diagnosis]]
strategy with the boring 95% amputated. Pays: levered longs in hype alts; persists because harvest needs
spot inventory + squeeze-wick tolerance + exchange risk no institution warehouses at size. Shape: lumpy,
10-40%/yr on deployed capital in active regimes, ~0 in dead ones, basis-blowout drawdowns.
DATA: HAVE (5y funding x 41 perps, 1h candles) — runs today.
PROBE Q: does gating on trailing-3-print mean funding >=30% ann. beat always-on carry?
PASS: pooled net yield (maker fees, measured turnover) >=8%/yr on deployed capital, >=10 symbols,
>=5 distinct episodes contributing, top-2 episodes <70% of PnL, positive in >=2 disjoint years.
Any miss = KILL. Cert risk: C5 (episodes cluster 2021/2024) — survivable, two manias in-sample. Use the
carry variant, not the win-rate ledger. Capacity dies low-7-figures/coin — irrelevant at user size.

**2. Hedged BNB Launchpool/HODLer harvest** — hold BNB spot, short BNB perp, farm every
Launchpool/HODLer airdrop, dump distributions instantly. Pays: Binance's user-acquisition budget —
projects pay emissions to BNB holders as the listing fee. Deliberate, indefinite, not an inefficiency.
DATA: CHEAP (historical Launchpool APRs public; BNB funding HAVE).
PROBE: trailing 24mo distributions minus BNB perp funding cost minus fees, on hedged notional.
PASS >=5%/yr net. KILL <5%. Pure arithmetic, ~2 hours, no engine.
Cert risk: doesn't fit the trade-ledger shape — it's a measured cashflow, closer to an invoice than an
edge. **Accept certification-exempt if the arithmetic clears.** Uncertainty is 2026 vs fat 2023-24 prints.

**3. Quarterly futures basis carry, regime-gated** — cash-and-carry Binance dated futures when
annualized basis >10% with >=30d to expiry, hold to convergence. Pays: longs wanting fixed-date leverage
without stochastic funding. DATA: CHEAP (one ccxt pull of quarterly candles; spot HAVE).
PASS: net (maker) >=5%/yr averaged INCLUDING flat periods, positive in >=2 disjoint regimes.
KILL: <5% avg or single-regime PnL. Cert risk C5 (basis fattens only in bulls) — if it fails there it
becomes a regime overlay for idea 1, not standalone. Huge capacity, tiny turnover.
**STATUS 2026-10-08: KILLED** (+3.94%/yr incl. flat; nothing qualifies since 2025-03) → [[f7-f3-killed]].

**4. Token unlock cliff shorts** — short perp T-7 before scheduled cliff unlocks >=1% of circulating
supply, cover T-0, portfolio across all events. Pays: VCs/teams with near-zero cost basis selling
mechanically per published distribution policy. DATA: CHEAP (DefiLlama/Tokenomist calendars free).
**Gating prerequisite: pull Binance data-dump DELISTED symbols first** or the short universe is
survivorship-poisoned — that ETL also un-bans future cross-sectional work, so do it regardless
(see [[b13-low-vol-fresh-lead]]: DB is currently pure-survivor, 0 delistings).
PASS: short-side net (taker RT 0.2% + funding paid) >= +0.5%/event, N>=80 events, block-bootstrap 95% CI
excludes zero, same sign in >=2 disjoint years. KILL: CI touches zero. Cert risk C1 (maybe only 100-200
events) → ensemble across venues/years for N>=300. Confidence medium-high; open question is
post-publication decay.

**5. Polymarket favorite-longshot calibration** — take the favorite side at 90-97c near resolution;
separately buy already-decided-but-unresolved markets under 99c. Pays: retail lottery preference /
identity bettors; favorite-longshot bias exists in every betting market ever measured.
DATA: CHEAP and fully RETROACTIVE — Polymarket API serves historical resolved markets, no collector, no
lookback decay. Scrape once, pandas forever.
PASS: realized win rate minus implied >= +1.5pp in the 90-97c bucket, N>=1000 contracts, gap stable
across >=3 categories (politics/sports/crypto). KILL: gap <= ~1pp fee+spread. Candle plumbing doesn't
fit but the calibration machinery maps 1:1; C4 nulls translate directly. Taxes: capital lockup to
resolution + UMA resolution risk. Best data-cost ratio on the list.
**STATUS 2026-10-08: KILLED** (favorites overpriced if anything, gap −1.53pp) → [[f5-polymarket-favorites-killed]].

**6. New perp listing funding capture** — first 7 days post-listing funding is chronically negative
(easy to short the pump on perp, no spot borrow exists); be the delta-neutral long collecting it where a
hedge leg exists. DATA: CHEAP (announcement archives scrapeable; Binance funding API history).
PASS: mean >= +0.5%/event net of hedge cost, positive in >=60% of events, on BOTH Binance and Bybit.
KILL below either. Cert risk C1 (~50-100 events) → ensemble across venues. **Flag: where no spot exists
the hedge leg vanishes and it degrades to naked long perp — report those separately, never blend.**
**STATUS 2026-10-08: KILLED both venues** (hit 45%/41%; mean is a tail; hedge = scarce borrow) →
[[f6-new-listing-funding-killed]].

**7. Funding-settlement clock scalp (00/08/16 UTC)** — when pending funding is extreme, fade the
pre-settlement dodge flow (funding very positive -> short T-30min, cover T+15min). NOT the banned
funding-direction signal ([[b16-funding-signal-refuted]]) — this is flow around the settlement timestamp,
sub-hour hold. Pays: position-dodgers closing/reopening on a clock, paying impact regardless of price.
DATA: CHEAP (one 1m-candle pull). PASS: mean gross move >= 2x maker RT fee, t>=3, N>=500, sign holds
out-of-asset and in >=2 years. **KILL if gross < 2x maker fee — do not proceed to net.**
**Pre-registered expectation: this dies** (C3 at fees; turnover brutal; maker-only makes it an execution
bet the rig can't settle). Two days to know. Low confidence, cheap kill.
**STATUS 2026-10-08: KILLED as expected** (fade −12bp/event, t −0.85) → [[f7-f3-killed]].

**8. Liquidation-cascade ladder bids** — resting bids laddered 1.5-4% below mid on liquid perps; fills
come from the liquidation engine's market orders; exit into reversion within minutes-hours. Distinct
from the banned post-shock reversal ([[plan-b-p1-results]]): entry is a resting order filled BY the
forced flow, not a signal after the bar. Shape: short-vol — many dimes, occasional steamroller.
DATA: HARD for real (liquidation + book collector — start this week, history accrues from day 1;
cf. [[liquidation-cascade-fade]]). PROXY probe NOW on 1m candles.
PROXY PASS: bars with low >=2.5% below prior close — mid recovers >=1.2% within 60min; fill-at-low
assumption yields mean >= 3x maker fee, 95% CI ex-zero, N>=300, positive in >=2 regimes.
**NOTE: fill-at-wick-low is a strict UPPER BOUND — a pass licenses the collector + micro-live ONLY,
never deployment.** Cert risk C6 fragility (tail fills) — correctly so, that IS the trade.
Best fit for the pre-authorized micro-live → this is where the 100 EUR goes.
**STATUS 2026-10-08: proxy PASSED 4/4 on spot** (+0.54%/event, N=2038) **AND on perp** (+0.51%/event,
N=2261). Recent-24mo clears 5%/yr only on touch-fills → [[f8-cascade-ladder-result]]. Collector BUILT +
RUNNING 2026-10-08 → [[bybit-liquidation-collector]]. Next: Bybit-native F8 rerun (proposed).

**9. Weekend variance risk premium (Deribit)** — sell delta-hedged short-dated BTC/ETH strangles Friday,
cover Monday; weekend realized vol systematically underruns short-dated IV. Pays: lottery-call buyers and
hedgers; VRP persists because the seller warehouses crash risk — which the user is explicitly authorized
to hold. DATA: HARD for real (no options plumbing in the engine, Tardis is paid — start an IV-surface
collector now). PROXY CHEAP: Deribit DVOL index history is a free API call; weekend RV from candles HAVE.
PROXY PASS: Fri-00UTC DVOL vs realized Fri-Mon vol, >=150 weekends, mean (IV - RV) >= 3 vol pts, t>=3,
positive >=60% of weekends, holds in each of 2022-2025. KILL: gap <= ~1.5 vol pts (est. spread cross).
Plumbing only on a fat proxy pass.
**STATUS 2026-10-08: KILLED.** Proxy passed but was the calendar effect; real Monday-expiry option
prints show no premium since 2023 → [[f9-weekend-vrp-killed]].

**10. Stablecoin depeg lottery bids** — permanent tiny resting bids on USDC/FDUSD/USDe pairs at
0.90-0.97, forever. Pays: panic sellers in bank-run hours (USDC printed 0.88 in March 2023, full
recovery). DATA: CHEAP (one pull of historical stable-pair candles).
PASS: recovery to >=0.995 within 14d in >=80% of sub-0.985 prints AND mean net >= +2%. KILL: recovery
<60%. N will be ~10-20 episodes: **stays UNPROVEN under C1 permanently, by design.** Hold it outside the
certificate as a standing option, or not at all. Probably ~zero EV most years; near-zero effort.

**BUILD ORDER (Fable's):** probes 1, 2, 3 today on stored data; the **Binance delisted-symbol ETL in
parallel** (gates 4 and all future cross-sectional work); scrapes for 5 and 6 this week; collectors for
8 and 9 started now regardless, since their lookback clocks only start when you do.

---

**BYBIT-ONLY DELTA (2026-07-31, Fable).** Execution constraint only — research still runs on Binance
dumps. Leverage caps per idea live in [[bybit-only-leverage-doctrine]], which also flags the
**MiCA/USDC-only conflict** that may shrink the tradable universe for 1/4/6/10.
1. **Unchanged, arguably better** — Bybit retail skew runs alt funding hot, perp universe wide.
   Re-pin fees to Bybit; the looser taker RT (~0.11%) also relaxes kill thresholds on 6 and 7.
2. **BNB version DEAD** (Binance-only). Replacement: **Bybit Launchpool/Earn** — many pools stake USDT
   (zero delta, no hedge leg needed at all) or MNT (MNTUSDT perp is live, hedge exists). Probe becomes
   pure arithmetic on trailing 24mo of Bybit pool APR-days. Honest flag: Bybit yields run thinner than
   Binance's and this may fail the 5% bar cleanly. Two hours to know.
3. Bybit lists **USDC-settled expiries on BTC/ETH only**, books thinner than Binance. Same probe,
   majors only, size down.
4. **Better on Bybit** — it lists small-cap perps faster and wider, so more tradable events. Event
   study still built on Binance dumps for delisted history; execution on Bybit perps.
5. **Survives** only because "Bybit only" means "my CEX is Bybit". If it ever becomes strict
   single-venue, this is out and nothing on Bybit replaces it. Keep it — best data-cost ratio.
6. **UPGRADED** — Bybit is the aggressive lister AND runs **pre-market perps for pre-TGE tokens**,
   where funding regularly pins the cap, sometimes on 4h/2h/1h intervals. No spot pre-TGE means no
   hedge leg: those are naked lottery positions, **separate bucket, never blended** with hedged
   post-listing carry.
7. **UPGRADED N** — Bybit's non-8h funding-interval symbols multiply settlement events. Same probe,
   add **funding-interval as a bucket dimension**.
8. Bybit v5 has the **`allLiquidation` websocket** (the old topic was throttled to 1 print/sec/symbol —
   use the new one). Start the collector this week. Live: isolated margin, **2-3x hard cap**.
9. Proxy probe unchanged (DVOL is free Deribit data; data isn't venue). Execution moves to **Bybit USDC
   options**: thin, wide; Paradigm RFQ exists but not at 100 EUR size. Plumbing only on a fat proxy pass.
10. **Drop FDUSD** (Binance ecosystem). Keep USDC/USDT, **add USDe/USDT** — Bybit is USDe's main CEX and
   Oct 10 2025 is already an in-sample event (USDe printed deep discounts, worst on Binance's book,
   recovered within days). Probe unchanged.
