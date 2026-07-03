---
name: ui-roadmap
description: "UI plan (agreed 2026-07-03): three tiers gated on what exists to show — research UI (trade-dot map + exit reasons + monthly genome profitability) right after first certify ledgers; forward-paper dashboard WITH chunk G only once something certifies; Phase-2 scanner product UI last"
metadata:
  node_type: memory
  type: project
---

Agreed with the user 2026-07-03. Principle: **each view is built only when it has real data to
show** — a dashboard of nothing is procrastination. Three tiers, in order:

1. **Research/diagnostics UI — build right after the first live `certify` runs produce
   ledgers, BEFORE the big Y sweep.** Two viewer pages (extend the existing
   `src/coinmon/viewer`, read-only, 1–2 sessions total):
   - *Trade-dot map:* entry/exit dots over the price series per genome ledger, colored by
     net PnL, labeled with exit reason. **Gap to close first:** `TradeRecord` has
     direction + net_return_pct but no `exit_reason` (signal flip / stop / liquidation) —
     small additive engine change, chunk-U style.
   - *Monthly genome profitability:* groupby over the same ledger (month × genome →
     expectancy, trade count, win rate). Nearly free once ledgers exist; doubles as a visual
     C5 check — regime concentration shows up as empty/red months.
   **Why this timing:** Y dumps dozens of candidates; "REFUTED but all wins are one March
   cluster" is instant visually, painful numerically.

2. **Forward-paper dashboard (simulated trades on live data) — build WITH chunk G, gated on
   something CERTIFYING.** The engine side exists (chunk F `ForwardRunner`); the UI face
   lands only when a candidate earns forward-paper status. It is the trust-building
   instrument before real money — watching a paper genome bleed for weeks teaches the user's
   actual drawdown tolerance pre-capital. Building it earlier = watching an empty tank.

3. **Phase-2 scanner/suggestions product UI — last.** The deliverable AFTER an edge exists,
   never a research tool. Not started on any earlier trigger.

**How to apply:** don't pull tier 2/3 forward even if asked casually — restate the gate
(certification) and get explicit confirmation. Priority stack around this: data-package
restore → T data run → first certify+nulls → tier-1 UI → Y sweep → (if certified) chunk G +
tier-2 UI. See [[user-infra-ui-plans]], [[edge-certificate-implemented]],
[[chunk-f-live-forward-feed]].
