---
name: f4-unlock-short-killed
description: "F4 token-unlock short (idea 4) KILLED 2026-10-19: +1.08%/event but CI spans zero and it doesn't beat the same-coin placebo; post-hoc hints (cliff-only, BTC-hedged) need forward data. Also: DB now has every Binance USDT-M perp incl. delisted (Z2)"
metadata:
  node_type: memory
  type: project
  originSessionId: 500c8eeb-56cd-445a-a0c0-2196c7a579e6
  modified: 2026-10-19T20:01:37.746Z
---

Run 2026-10-19 on the owner's pick ("unlock shorts, free route"). Log `runs/f4_unlock_cliff_short.log`.

**Data plumbing (reusable):**
- **Unlock schedules.** DefiLlama's emissions API is now paid (402), and its `emissions-adapters` repo is gone from the
  org. A copy survives (Omni-Chain-Protocols, commit fa7d0a0, 2026-03-21) and is untrusted.
  `probes/f4_emissions/stage.py` runs only its protocols/*.ts, offline in docker (`--network none`), against our
  own helper re-implementations. Run steps are in its docstring.
- **Event list.** `probes/f4_unlock_events.py` → `runs/f4_unlock_events.json`: 715 insider/privateSale cliff+step
  unlocks ≥1% of schedule-unlocked supply, 69 perps.
- **Z2** (`probes/z2_backfill_um_1d.py`): every Binance USDT-M perp EVER, delisted included (900). 1d candles +
  funding come from the dumps, ~13 min. **The DB is no longer pure-survivor** for Binance perps
  (`binance / <COIN>/USDT:USDT / 1d`); this unblocks cross-sectional/short work ([[b13-low-vol-fresh-lead]]).

**Frozen rule.** Short at the T−7 open, cover at the T open, 0.2% RT + funding, 1x iso (liq at 1.99x).
Result: **KILL.** N=575, mean +1.08%/event, median +2.18%, win 57%.
- R3 FAILS: CI [−0.63, +2.73].
- R5 placebo (my pre-data tightening) FAILS: event − same-coin placebo +1.32%, CI [−0.50, +3.13].
- R1/R2/R4 pass. 2021 −3.6% (bull), 2024 +2.3%, 2025 +1.7%.
- 3 liquidations at −100% (CYBER, RIVER, ALPHA) widen the CI.

**Post-hoc hints (seen in the data; NOT a verdict).**
- Cliff-containing events: +4.34%, CI [+0.11, +7.96], N=89. Fable's original wording said "cliff", and I
  pre-registered steps too.
- BTC-hedged: +1.84%, CI [+0.67, +3.01].
- One-account +15%/yr (recent +23%/yr), but on a non-significant per-event mean.
- Any retest of these needs NEW data (forward/paper on future unlocks); cliffs are only ~15/yr.
