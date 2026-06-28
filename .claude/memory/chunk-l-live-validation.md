---
name: chunk-l-live-validation
description: "Live run that validated chunk L's leverage fix (GA stopped chasing leverage) but surfaced the real remaining blocker: regime non-stationarity + zero graduation GOs ever on live data — next is proving the gate is passable, not making ETH pass"
metadata:
  node_type: memory
  type: project
  originSessionId: continue-2026-06-28
---

**Live validation run for chunk L, 2026-06-28** (`coinmon search --timeframe 1d --holdout 0.2
--stress 80`, seed 0, pop 30, gens 12, against the Docker DB).

**Leverage fix VALIDATED — this is chunk L's deliverable, proven.** The GA winner flipped from the
pre-L `atr_channel 4.6x perp short` (a leveraged blow-up) to a sane `atr_channel ETH/USDC long/flat
spot` (mult 0.5, period 19 — no leverage, no stop). Worst-fold drawdown 100%→33%; per-fold went from
leveraged noise `+169%/-100%/+1046%/+1784%` to a steady `+27%/-3%/+45%/+81%` (median +36%, 26 trades).
Part B (convex drawdown penalty) + Part A (intrabar stop gene) **killed the reckless-leverage attractor**
exactly as designed — the search now spends its budget on low-drawdown genomes, not blow-ups. Closes
[[leverage-breaks-fitness-scaling]].

**But still NO-GO (holdout -45.7%), and the diagnostic overturned our working intuition.** I graduated
every directional variant of the winner on the SAME ETH/USDC holdout:
- long/flat spot (winner): **-45.7%** (beats B&H -57%)
- 2x perp short, no stop: -79.8%
- 2x perp short, 15% stop: -78.1%
- 3x perp short, 15% stop: -93.5%

The **"downtrend holdout → add a short and it graduates GO" intuition is FALSE** for trend-following
breakout on this data. ETH/USDC's most-recent 20% (331 bars) isn't a clean slide — it's a -57% *choppy*
crash with violent bear rallies. ATR-channel shorts get whipsawed/squeezed and lose MORE than the long
that merely sidesteps; the stop doesn't help (it re-shorts into the next squeeze). So NO config of this
family survives this regime → the gate correctly NO-GOs all of them. **This is correct, safe behavior,
not a calibration bug** — deploying any variant into the next regime would have lost money, and the gate
caught it. The leverage/brake problem is closed; the remaining NO-GO is **regime non-stationarity**.

**The actionable concern: many NO-GOs, ZERO GOs ever on live data** (this run + the 5-seed sweep in
[[first-live-search-graduation]]). The next priority is NOT to make ETH pass (that's the overfit trap
[[search-overfits-not-strategy]] warns against) but to **prove the graduation gate is even passable**:
sweep pairs/timeframes where the recent holdout isn't a single-regime crash and confirm at least one
sane genome graduates GO.
- If something GOs → pipeline fully validated; ETH's NO-GO is just that pair's regime → proceed to chunk G.
- If nothing ever GOs → the absolute-return-on-recent-tail gate may be unachievable by construction;
  revisit the gate design (the relative / risk-adjusted holdout criterion the user set aside in
  [[first-live-search-graduation]] — reopen it now that the evidence has piled up).

**RESOLVED 2026-06-28 — sweep done: the gate IS passable; the binding cause is the direction gene.**
Cheap regime scan first: the WHOLE recent market crashed — every USDC pair / ETH-or-BTC ratio's recent-20%
holdout is -10%..-65%; only **BNB/ETH (+13.7%)** and **BNB/BTC (+2.8%)** have a survivable holdout (BNB
outperformed lately). That alone explains the zero GOs: prior runs searched the full UNIVERSE and the GA
kept landing on pairs whose holdout is an unsurvivable crash. Restricting the pair gene to the two
survivable pairs and running the real `run_search` (pop30/gen12/stress80, holdout 0.2): winner
`rsi_meanreversion BNB/ETH 1.0x perp SHORT` graduated NO-GO by a whisker (holdout **-0.92%**, frag 2%) on a
**+13.65%** holdout — it SHORTED an up regime. **Then the proof:** graduating the SAME genome as
**long/flat spot** → **GO (+8.50%, 14 trades, 100% fragility).** So the gate is passable and the pipeline
blesses a strategy — it is NOT too strict, and the gate design does NOT need reopening.

**The real finding → [[direction-gene-overfits-regime]]:** every live NO-GO failed on the DIRECTION gene,
which the GA fits to the search span while blind to the holdout regime (ETH/USDC picked long→holdout
crashed; BNB/ETH picked short→holdout rose). The winning params were fine; only the direction bet was wrong.
The fix is a regime-ADAPTIVE representation (long bullish / short bearish, signal-driven), not a coin-flip
`short` gene locked in by in-sample fitness. Tie back to [[build-roadmap]] (chunk L done & validated).
