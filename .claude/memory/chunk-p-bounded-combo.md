---
name: chunk-p-bounded-combo
description: Chunk P bounded multi-indicator genome — a FIXED-shape combo (N indicators + AND/OR) registered as a normal family; scale-free unit genotype solves the cross-indicator threshold problem; the GP half-step before tree-GP (Q)
metadata: 
  node_type: memory
  type: project
  originSessionId: 6228a1b7-55e8-4106-a7b7-2c7e61920b0e
---

Chunk P (2026-06-28). The risk-managed GP half-step before unbounded trees (Q): the MACHINE
composes a small program instead of us hand-writing strategy templates, but the shape is CAPPED so
the overfit surface grows by a controlled, watchable amount.

**What it is:** `strategies/indicator_combo.py` — a fixed-shape genome that picks `N_CONDITIONS`
(=2; a module constant, generalises to 3) indicators from a curated pool, each an
`(indicator, period, op ∈ {<,>}, threshold)` predicate, joined by one AND/OR `combine` gene → long
when the combined rule fires, flat otherwise. NO separate entry/exit band (the same predicate enters
and exits) — a churny rule just pays fees and OOS fitness rejects it; that's the honest signal.

**The key architectural win — it's just another family.** Registered as
`genome.FAMILIES["indicator_combo"]`, so chunk P reuses the WHOLE pipeline UNCHANGED: GA
sample/mutate/crossover, `decode`/`decode_portfolio` (an adaptive combo wraps in RegimeAdaptive and
trades a perp like any family), OOS fitness, graduation, cross-pair (chunk O). The only edits beyond
the new file: the family registration in `genome.py` + an optional `StrategyFamily.describe`
(renders the winner's composed rule readably, e.g. `rsi(14) > 72.3 AND ema_dev(20) < -0.012`,
surfaced in `SearchReport.summary` — flat genes are otherwise opaque). This is the same
representation-agnostic seam Q will reuse (a tree also compiles to a `Strategy`).

**The threshold-scale problem and its fix (the heart of P).** Indicators live on incomparable
scales (RSI 0..100; a MACD histogram is in price units that differ 1000× across pairs), so one
uniform threshold gene can't be meaningful across them. Fix = a SCALE-FREE genotype: `period` and
`threshold` are stored as unit [0,1] genes, and each indicator's `IndicatorSpec` maps the unit onto
its OWN natural range at decode time. The GA mutates one uniform schema while every indicator still
gets sane periods/thresholds — the standard GP genotype/phenotype-decoupling trick.

**Curated pool (6, all pair-scale-INVARIANT):** rsi, trix, tsi, macd_hist/close, (close−ema)/close,
atr/close. The cumulative-volume N5a indicators (OBV/AD/PVT) are deliberately EXCLUDED — their
absolute level is pair-scale-dependent, so an honest threshold needs a "vs own trend" normalisation
(a different shape; clean follow-on). MACD couples slow=2×period, signal=period//2 to stay on one
period gene. During any indicator's warmup (NaN) the position is HELD (rule undefined → no trade on
partial evidence). Point-in-time by construction (only streaming values up to now), so live-parity
holds. Combo is explored by EVERY `search`/`sweep` by default — that IS the point of P.

229 tests green (+16; bit-of-note: a 1000× price-scale invariance proof on macd_hist/ema_dev),
ruff clean. **NOT yet run live** — the chunk-P verify is a user run
(`search --timeframe 1d --holdout 0.2 --stress 80 --cross-pair 5`): does the O-hardened gate hold
its false-GO rate against this bigger-but-bounded surface? Yes → earned the right to go unbounded
(Q). No → the judge needs more work, discovered cheaply without building the tree machinery.
See [[build-roadmap]], [[chunk-o-cross-pair-robustness]], [[n5a]] (N5a indicator library),
[[search-overfits-not-strategy]] (more surface = more overfit room, not more alpha).
