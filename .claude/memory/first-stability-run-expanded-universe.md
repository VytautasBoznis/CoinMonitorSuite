---
name: first-stability-run-expanded-universe
description: "First live `coinmon stability` run (chunk S), on the T-expanded 496-pair universe: a clean calibrated NEGATIVE — no GO in any window, winners hop pairs/families, forward persistence 0/2, and every winner is trade-starved (4-13 trades, under the 15-floor). Confirms the plan's §0 diagnosis; gate held on 496 pairs."
metadata: 
  node_type: memory
  type: project
  originSessionId: cc8b2997-71e4-4d25-8616-f5545e120e1e
---

2026-07-02. Ran `coinmon stability --timeframe 1d --holdout 0.2 --stress 80` for the first
time (chunk S was built but never run; its prerequisite was more data, now met by T).

**Setup:** 496 auto-built pairs (~31 USDC bases, up from 15). 3 rolling 60%/20% windows.

**Result — a clean calibrated negative (as [[search-overfits-not-strategy]] /
[[nested-holdout-refutes-golden]] predict):**
- No GO in any window. Winners hop: 3/3 distinct pairs, 2/3 families, param drift 0.27.
- Forward persistence 0/2 — neither window's winner survived the next window's unseen bars
  (−33.89%, −4.09%). Passing a window's gate bought nothing forward.
- **Trade starvation is binding:** winners had 4 / 6 / 13 trades — all under the 15-trade
  floor, so most NO-GOs are EVIDENCE failures, not return failures. Exactly the §0
  sample-starvation diagnosis; the direct motivation for U (pool to N≥300) and X (4h).
- The gate HELD on the 496-pair surface: NO-GO'd a +15.69%/4-trade winner and a −55% blow-up.
  More pairs = more lottery tickets, judge not fooled.

**Methodology catch:** this ran on the USDC universe (`discover_universe` still defaults to
`quote_currency=USDC`), which [[train-usdt-certify-usdc]] says must stay pristine for final
certification. Contamination is negligible (the diagnostic selected NOTHING to carry forward,
so no choice was tuned to it), but it confirms the wiring chunk U must add: **search targets
USDT, USDC reserved.** Interim mitigation: `COINMON_QUOTE_CURRENCY=USDT` before search/stability.

Net: reinforces the whole [[alpha-definition-edge-certificate]] plan — daily price-shape rules
carry no stable edge; the fix is pooled per-trade evidence + nulls + new families, not more
search on the same valley.
