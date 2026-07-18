---
name: anomaly-hourofday-lead
description: "FIRST path-to-hurdle ANOMALY (2026-07-18, anomaly-focus pivot). Built an anomaly scanner (probes/anomaly_scan.py); it found the 21:00-23:00 UTC (US-session-close) hour-of-day effect. B20 confirmation PASSED out-of-sample: all 5 binance 1h majors net-maker positive (median +16%/yr), significant out-of-ASSET (BNB t=6.0, ETH t=4.67), coherent window plateau (not cherry-picked), beats all-windows baseline 5/5, recent-half +11%. BUT edge exists ONLY at maker fees (net-taker -30 to -52%/yr) and needs 52-90% MAKER FILLS to stay positive -> deployability is a maker-execution bet, must be validated by live-paper fill measurement. Cross-sectional factors (low-vol/oi-decrowd/momentum/etc.) all sub-threshold (|gross_t|<3)."
metadata:
  node_type: memory
  type: project
  originSessionId: SESSION_2026_07_18
  modified: 2026-07-18T14:42:20.525Z
---

**The pivot (user, 2026-07-18):** "I accept there might not be an actual edge, but I'd expect
ANOMALIES — focus on that." Bar chosen = **"path to the deploy hurdle"** (an anomaly counts only with a
plausible route to >=5%/yr forward, alone or combined — [[live-yield-hurdle]] discipline kept, sources
widened). Approach = "all three eventually (scanner-map / exploitable-dislocations / combine-weak-signals),
now rank by fastest-doable and start there." Fastest tier = zero new data on the existing panel.
See [[riskier-strategies-allowed]], [[mission-find-edge-ship-ui]].

**The scanner (durable tool): `probes/anomaly_scan.py`** (log `runs/anomaly_scan.log`). Measures a
battery of anomalies on the existing data and — key design — separates "is the effect REAL" (GROSS
t-stat) from "can it PAY" (NET long-short spread at taker vs MAKER fees, using measured turnover).
Reuses the 41-perp bybit USDT 1d panel + funding + the 5yr OI backfill, plus binance 1h majors for
calendar/microstructure. Extensible; this was the first run.

**Cross-sectional factor map (all SUB-THRESHOLD).** Ranked by gross_t: oi-decrowd(30d) t=2.55,
low-vol(30d) t=1.72, ST-reversal(3d) t=1.42, momentum t=1.03, low-funding t=0.53, illiquidity t=-0.75.
At LOW turnover (H20, quintile, maker) the top factors show large NET spreads (+37-43%/yr) but NONE
clear |gross_t|>=3 (borderline after ~14 tests), and the arithmetic spread OVERSTATES a real
compounding book — B18's OI neutral book already LOST when actually traded ([[session-2026-07-18-tsmom-oi]]).
So no cross-sectional factor has a standalone path; the strongest (oi-decrowd, low-vol) are
combine-candidates at best. Consistent with every prior negative.

**THE LEAD — hour-of-day (US-session-close), FIRST anomaly with a path to the hurdle.**
Scanner found BTC 1h mean return significant at 21:00 UTC (t=3.63) and 22:00 UTC (t=3.08), 23:00
negative. Confirmation probe `probes/b20_hourofday_window.py` (log `runs/b20_hourofday_window.log`),
pre-registered: hold the [21:00,23:00) UTC window long each day, flat 22h; the window was DISCOVERED on
BTC so BTC is in-sample — the honest tests are OUT-OF-ASSET (ETH/BNB/XRP/SOL) and OUT-OF-TIME (recent
half). Result **PASS**:
- All 5 majors net-maker positive: BTC +16.1%, ETH +22.7%, BNB +27.9%, XRP +14.8%, SOL +6.0%/yr;
  median +16.1%/yr. Positive 5/5, beats all-24-windows baseline 5/5, recent-half median +11.2%/yr.
- Out-of-ASSET gross significance is strong: BNB t=6.00, ETH t=4.67, XRP t=2.94 (majors are correlated
  so ~2 effective independent tests, but adjacent-hour + structural story make it hard to dismiss).
- WINDOW ROBUSTNESS: a coherent plateau (hold 20-22 +9.2%, 21-23 +16.1% peak, then collapses 22-00
  -9.3%) — not a cherry-picked single hour. Real US-afternoon/close microstructure signature.

**THE HONEST GATE (why it is a lead, not yet a deployable winner):**
- Net-TAKER is -30 to -52%/yr — the edge exists ONLY at maker fees (per-day edge ~0.08% < taker
  round-trip 0.2%).
- MAKER-FILL SENSITIVITY: needs 52-90% maker fills to stay net-positive (BTC 72%, ETH 61%, BNB 52%,
  XRP 75%, SOL 90%). Timed directional entries suffer ADVERSE SELECTION (you get filled when price is
  about to move against you). The +16%/yr assumes near-perfect maker fills at the reference price —
  optimistic. **Deployability is a maker-execution bet that only a LIVE-PAPER fill measurement can settle.**
- 1h data exists for only 5 binance majors; broader out-of-asset evidence + a diversified basket (which
  tolerates more taker fills) needs 1h collection for more coins (fast scraper add).

**Recommended next steps (for the user):** (1) live-paper the window with real maker limit orders to
MEASURE actual fill rate vs the 52-90% breakevens — the decisive test; (2) collect 1h candles for the
wider universe to widen evidence + enable a diversified basket; (3) combine with the sub-threshold
cross-sectional factors (approach 3). This is the strongest result the project has produced — the
anomaly-focus reframe paid off on the first fast probe. Still 0 CERTIFIED/deployable, but the first
real candidate. See [[autotrading-rollout]] (maker execution mode), [[plan-b-fallback-probes]].
