---
name: live-yield-hurdle
description: "USER GATE (2026-07-06): certified != worth deploying. Live real capital requires an EXPECTED FORWARD, CONTINUING net yield >= 5%/yr after all real frictions. Below that a strategy is negative EV — infra/attention cost + opportunity cost vs a passive index fund that pays more for zero effort. Weight the RECENT regime, never the flattered full-sample."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b74a3a98-2baf-46d6-ab1c-f5df1fde6b6e
---

User directive, 2026-07-06, after carry certified at ~+2.2%/yr: a CERTIFICATE proves an
edge exists; it does NOT mean deploy. The deployment decision is profitability-vs-alternatives,
and the user's floor is an **expected forward, continuing net yield of >= 5%/yr** (after ALL real
frictions: borrow, spread/basis beyond taker, execution slippage, and the infra/attention cost of
running it in the k8s cluster).

**Why:** below ~5%/yr the strategy is not merely irrelevant, it's value-DESTROYING — it costs
money and attention to run, and the same capital in a passive index fund returns more with zero
effort. A thin certified edge that loses to an index fund is not a reason to trade.

**How to apply:**
- Before recommending ANY live/micro-live (even ~$10), check: expected forward net yield x feasible
  leverage >= 5%/yr, AND expected to persist. If not, keep it as MONITORING/paper only.
- Use the RECENT regime as the forward estimate, never the full-sample number (the full sample is
  flattered by older high-yield eras — see carry below).
- Micro-live for "execution validation" is only worth it if the strategy is actually a live
  candidate under this hurdle. Validating fills for something you won't run is wasted effort.

**Carry vs this hurdle (the settling calc):** certified full-sample +2.23%/yr, but the two regime
means annualize to ~+4.9%/yr (older half) vs **~+0.18%/yr (recent half)**. At the RECENT premium
even 3x leverage on the neutral book is ~0.5%/yr — nowhere near 5%. Carry only clears the hurdle if
the funding premium reverts toward the older-regime level (then ~5%/yr at 1x, ~15%/yr at 3x). So:
**carry is CERTIFIED but does NOT currently clear the deploy hurdle** → it becomes a MONITORED
candidate that goes live only when the funding premium widens back to a harvestable level. This
reframes [[w3-carry-first-live-diagnosis]]'s "micro-live unlocked" — certification unlocked it in
principle; this yield hurdle keeps it parked until the premium is rich enough. See
[[autotrading-rollout]], [[mission-find-edge-ship-ui]].
