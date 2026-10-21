---
name: c1-cross-coin-contagion-killed
description: "C1 cross-coin cascade contagion KILLED 2026-10-21 (owner idea 2, minute scale): cascades spread (x31 lift) but laggards don't follow far enough to pay; F8 fills after another coin's crash no better. Post-hoc: same-minute market-wide crash fills are F8's worst (+0.23% vs +0.6%)"
metadata:
  node_type: memory
  type: project
  originSessionId: b07cd4d1-531d-4981-a504-2599f052cef5
  modified: 2026-10-21T17:08:49.672Z
---

Owner idea 2 from [[swarm-and-cross-market-ideas]] ("if a coin crashes in one market, prep in another"),
tested at 1-minute scale across coins. Probe `probes/c1_cross_coin_contagion.py`, log
`runs/c1_cross_coin_contagion.log`. Data: Binance USDT-M perp 1m, F8's 10 coins, 2021-01 → 2026-09.
- **Episode:** a coin hits F8's ±2.5% trigger after 60 quiet minutes. Down: 920 episodes; up: 969.
- **Test strictness:** three tests, so Bonferroni 98.33% day-cluster intervals.

**Results, all FAIL:**
- **Contagion is real as a probability.** After an episode, a laggard triggers within 15m 4.9% of the time vs
  0.161% in any window (×31). Up-episodes ×17.
- **T1-DOWN:** short laggards from the t+1 open to the t+15 close at HL taker. −0.109%/event, CI
  [−0.198, −0.019]: significantly NEGATIVE. Gross −0.019%: laggards don't follow. Every horizon 1-60m is negative.
- **T1-UP** (long laggards after pumps): −0.072%/event, CI spans 0.
- **T2:** F8 fills LED by another coin's trigger in the prior 15m earn +0.658% (N 636) vs ISOLATED +0.596%
  (N 970). Diff CI [−0.29, +0.39]. The self-check reproduced F8 perp exactly (N 2261, +0.509%).

**Post-hoc, NOT verdicts:**
- BTC-led T1-DOWN is +0.64% but N is only 161 events (≈18 episodes).
- Fills where another coin triggers in the SAME minute earn +0.234% (N 655), far worse than isolated or led.
  These are the market-wide crashes. At 1m there is no time to react. Only sub-second data could show whether
  a lead exists to pull the bid first. That is the one sharpened question left for the cross-venue collector
  (phase C).

Related: [[f8-cascade-ladder-result]], [[plan-b-p1-results]] (B3/H4, the slower lead-lag kills).
