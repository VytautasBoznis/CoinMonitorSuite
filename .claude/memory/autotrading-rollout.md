---
name: autotrading-rollout
description: "Auto-trading plan (2026-07-04) — suggestion UI with confirm, per-strategy execution mode graduating suggest-only → auto-on-confirm → capped full-auto"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

Agreed rollout for automated trading (2026-07-04), keeping the earlier "UI shows suggestions,
user confirms, with ability to auto-execute" plan, refined to be PER-STRATEGY with a
graduation path rather than a global switch:

1. **suggest-only** (default for every new strategy): the viewer (src/coinmon/viewer/,
   Dockerfile.viewer) surfaces the signal + sizing; the user executes manually / confirms.
2. **auto-on-confirm**: one-click execution of the suggested order. Unlocked when the
   strategy is CERTIFIED by the edge-certificate gate.
3. **full-auto with hard position caps**: unlocked only after certification AND a paper-
   trading track record consistent with the backtest.

**Why per-strategy:** execution latency tolerance differs wildly. Funding carry rebalances
slowly — confirm-mode costs nothing, making it the natural first semi-auto candidate.
Cross-sectional momentum rebalances weekly — confirm-mode is fine indefinitely.
Liquidation-cascade fade has a minutes-wide window — confirm-mode is unusable; it either
runs full-auto-with-caps once trusted, or isn't traded.

**How to apply:** when building the live layer (src/coinmon/live/ exists), model execution
mode as a per-strategy enum with the gate conditions above enforced, not configurable
around. Related: [[ga-parked]], [[execution-plan-2026-07]].
