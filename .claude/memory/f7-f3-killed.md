---
name: f7-f3-killed
description: "F7 funding-settlement clock scalp KILLED (fade loses -12bp/event, extreme funding nearly extinct since 2025) and F3 quarterly basis carry KILLED (+3.94%/yr incl. flat, no qualifying trade since 2025-03), both 2026-10-08. Same premium-decay pattern as F1/F8/F9/W3."
metadata:
  node_type: memory
  type: project
  originSessionId: 4238af7c-0366-4df9-991c-17ffbd36d05d
  modified: 2026-10-08T18:26:16.080Z
---

Ideas 7 and 3 of [[fable-batch-10-probe-queue]], run 2026-10-08.

**F7 funding-settlement clock scalp — KILL** (`probes/f7_funding_clock_scalp.py`,
`runs/f7_funding_clock_scalp.log`). Binance funding for the 10 F8 perps now stored as
`funding_rates` exchange `binance` (2021-01 → 2026-09). Events: previous settlement |f| >= 0.05%
(strict point-in-time), N=3384, 930 clusters. Fade T-30 → T+15: **−12.1bp, cluster t −0.85**, 9/10
symbols negative. Snooped split: T-30→T ≈ 0, T→T+15 −12bp (t −2.35) = payers REOPEN after settlement.
Funding collected doesn't rescue it (−6bp net). 77% of events are 2021; 2025 had 18, 2026 5 —
extreme funding on majors is nearly extinct, so even the snooped reverse has nothing to harvest.

**F3 quarterly basis carry — KILL** (`probes/f3_quarterly_basis_carry.py`,
`runs/f3_quarterly_basis_carry.log`). Binance USDT-M BTC/ETH quarterlies (continuous klines,
2021-02 →), gate b > 10% ann & dte >= 30d, hold to delivery, 0.5x book. 20 trades all positive
(locked), deployed 52%, **+3.94%/yr incl. flat** (Q1 needs 5%); years 8.5/4.0/1.3/7.4/1.5%.
**No qualifying trade since 2025-03**; recent 24mo +1.33%/yr (1x unified book: +2.65%). Fable's
fallback: usable only as a regime overlay for [[f1-tail-gated-carry-result]], not standalone.

**Cross-probe pattern (now 6 for 6):** every structural premium found (W3 carry, F1, F3, F8, F9) was
fat in 2021-22 and decayed to under the 5%/yr [[live-yield-hurdle]] in the recent 24 months.
