---
name: b13-low-vol-fresh-lead
description: "Fresh-ideation pivot (2026-07-06) after P1/P3 exhausted: the cross-sectional LOW-VOLATILITY anomaly. B13 (long-only) PASSED its frozen rule but underperforms BTC-hold. B14 (market-neutral long-low-vol/short-high-vol, honest perp-funding short costs) ALSO PASSED its frozen rule (12/12 net-positive, median +72%/yr) — BUT risk-adjusted it is NOT a winner: Sharpe 0.79-0.90, maxDD -64% to -82%, negative in 2023-2024, and survivorship-inflated short leg. It's a regime-timed short-vol/crash-hedge bet, not clean alpha. Low-vol lead now essentially exhausted; still 0 deployable winners."
metadata:
  node_type: memory
  type: project
  originSessionId: 0bad2d36-e6f2-4947-bbf3-a97230196573
---

2026-07-06 session. After Plan-B P1 (all FAIL) and P3 (B10 FAIL, B9 ran → 1/7, does NOT fund Z3;
see [[plan-b-p3-results]]) exhausted the cheap price-shape/cost-side probes, the user chose "pivot
to fresh ideation" (mission step 1d, [[mission-find-edge-ship-ui]]). Web research (2024-2026 crypto
asset-pricing literature) surfaced two fresh, retail-reachable, candle-only candidates NOT in the
exhausted valley:
- **Cross-sectional LOW-VOLATILITY anomaly** (the lead) — low-vol coins earn higher future returns;
  documented as EMERGING/STRENGTHENING in recent/mature crypto data (matches the [[live-yield-hurdle]]
  recent-regime requirement). Distinct from W5 momentum (rank by RISK, not return; long leg is the
  STABLE coins → less fee churn).
- **Hour-of-day seasonality** (21:00-23:00 UTC / NYSE-closed window) — queued as B15, uses 1h candles,
  but fee-fragile (many round-trips); untested (only weekday H2 was, and FAILED).

**B13 low-vol probe RUN → PASS on the frozen rule, but NOT a deploy winner long-only.**
`probes/b13_low_vol_xsection.py` (log `runs/b13_low_vol_xsection.log`), frozen rule pre-registered in
the docstring BEFORE running (b9/b10 pattern): rank the 41 Bybit USDT DIRECT legs (1d) by trailing
realized vol, long the bottom-`q` slice equal-weight, monthly hold, vs EW-universe benchmark; fixed
12-config grid (L∈{30,60,90}×q∈{0.2,0.3}×reb∈{14,30}), PASS iff ≥9/12 positive full-sample edge AND
median recent-half edge >0. Reuses `load_universe_closes`+`summarize` (W5 code untouched).
Result: **12/12 positive edge vs EW-universe, median recent-half edge +88%, +20.7%/yr edge.**
**HONEST CAVEATS (why it's a lead, not a winner):**
- The EW-alt benchmark CRATERED −66% to −78% (2021-2026 alt bear), so "beats benchmark" is a low bar
  — same edge-vs-dying-beta trap W5's short leg hit ([[xsectional-momentum-first-run]]).
- Long-only ABSOLUTE return: median +28% total = **+5.6%/yr**, which **UNDERPERFORMS BTC buy-and-hold
  +78% (+15.6%/yr)** over the same span. Only the concentrated q=0.2 configs (+99% to +148% abs) beat
  BTC. Per the deploy hurdle the real alternative is BTC/index, not the alt basket → long-only FAILS
  that bar.
- ~40% per-position win rate on every config → returns are right-skew (a few trending low-vol coins),
  a fragility flag.

**NEXT (the real test — B14, market-neutral):** the −70% benchmark means HIGH-vol coins got destroyed,
so the documented alpha lives in the **long-low-vol / short-high-vol MARKET-NEUTRAL** book: removes the
BTC-beta comparison problem (neutral vs cash → hurdle is absolute yield, like carry), captures the
high-vol-underperformance short leg, and reuses the carry/perp infra. MUST pre-register B14 with an
HONEST short-side cost model (perp funding + borrow on high-vol alts, which is expensive/scarce) —
don't rush it and inflate the result. Then a full Edge Certificate (absolute expectancy CI + ≥2
regimes + the 3 nulls, NOT edge-vs-beta) via the xsectional certify path. If B14's neutral book clears
absolute expectancy + the 5%/yr hurdle after short costs, it's a genuine winner candidate (1 of 3).
Still **0 deployable winners** toward the UI gate. See [[plan-b-fallback-probes]], [[portfolio-search-protocol]].

**B14 RUN (2026-07-06) → PASSED the frozen rule, but NOT a deploy winner.** `probes/b14_lowvol_neutral.py`
(log `runs/b14_lowvol_neutral.log`). Dollar-neutral long bottom-vol / short top-vol PERPS on the 41
Bybit USDT legs, 1d; honest short cost = real per-symbol Bybit 8h funding summed to daily, applied per
bar with correct sign (long pays / short receives — the same funding data that CERTIFIED carry,
[[w3-carry-first-live-diagnosis]]); both legs on one margin account (harsher/executable version). Frozen
rule pre-registered: grid L∈{30,60,90}×q∈{0.1,0.2}×reb∈{14,30}; PASS iff ≥9/12 net-positive AND median
annualized ≥+5%/yr (applied DIRECTLY — neutral book has no beta to subtract) AND median recent-half >0.
Result: **12/12 net-positive, median +72%/yr, recent-half +82%, survives fee×2+25% funding-haircut
fragility.** Funding was a mild tail-wind (short leg received ~+0.1-0.3% per hold on avg).
**WHY IT IS STILL NOT A WINNER (risk metrics I added post-run — the frozen rule was blind to these):**
- **Sharpe only 0.79-0.90** — the +100-600% totals are leveraged variance (gross 2, high-vol short leg),
  NOT a strong edge.
- **maxDD -64% to -82%** — undeployable; worse drawdown than just holding BTC.
- **Regime-driven, short-gamma**: enormous in the 2022 alt crash (+136%/+341%), NEGATIVE in 2023
  (-36%/-14%) and one config in 2024 (-9%). A crash-hedge / short-alt-vol bet, not a neutral money machine.
- **SURVIVORSHIP UNADDRESSED**: the 41-coin universe = today's SURVIVING liquid Bybit legs; high-vol
  alts that went to zero and delisted are absent — exactly where the short leg's bias inflates returns.
Did NOT run an Edge Certificate — it would only formalize a strategy the risk metrics already disqualify.
Fork for the user: (a) accept it as a crash-HEDGE overlay (not standalone alpha), (b) attempt a
survivorship-clean universe (needs delisted-coin history we likely lack), or (c) move to Plan C on-chain
([[plan-c-onchain-ideation]]).