---
name: first-golden-structural-edge
description: "First GOLDEN tier ever: a big 30-seed grind found rsi_meanreversion on BNB/ETH (regime-adaptive 2x perp) that beats B&H on an UP regime and generalizes across 4/5 decorrelated peers — the project's first candidate structural edge (not a crash-short)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6228a1b7-55e8-4106-a7b7-2c7e61920b0e
---

**⚠️ REFUTED — read [[nested-holdout-refutes-golden]] first.** A strict temporal nested holdout
showed this "golden edge" was a regime-specific data-mined artifact (move the holdout window and 0
golden appear, the RSI(2) genome never recurs, dev-GO genomes go 0/2 out-of-sample). Keep this note
as the record of how it looked BEFORE the decisive test — not as a live finding.

The big grind, 2026-06-28. `sweep --timeframe 1d --population 300 --generations 80 --seeds 30
--folds 10 --embargo 5 --min-trades 25 --holdout 0.2 --stress 300 --cross-pair 5 --cross-pair-min 3
--graduate-min-trades 15 --workers 0`. ~48 min, 12 cores pinned (N2 parallelism finally in its
winning regime — large per-generation batches). 15-pair universe, 4 families incl. chunk-P combo.

**FIRST GOLDEN EVER — and it's not a crash-short.** Winner class `rsi_meanreversion on BNB/ETH`,
regime-adaptive 2.0x perp, 50% stop, params `period=2, oversold=38.9, exit_level=72.8`:
- Holdout **+29.1% vs B&H +13.65%** — B&H was POSITIVE, so this BEATS buy-and-hold on an UP regime.
  Every prior GO in project history was a leveraged perp SHORT riding a down regime
  ([[regime-adaptive-multiseed-sweep]], [[first-live-combo-cross-pair-sweep]]); this is the first
  structural-direction edge that makes money when the market rises.
- Fragility 300 runs: 100% positive, 100% beat B&H.
- Cross-pair **GOLDEN — held on 4/5 decorrelated peers** (same genome, pair gene swapped via
  chunk O): BTC/XRP +21%, BNB/USDC +15%, ETH/XRP +141%, BNB/SOL +61%; only SOL/XRP missed (86%
  fragility, just under the 90% bar). The edge GENERALIZES across unrelated pairs = structural, not
  the pair-specific curve-fit chunk A warned about.
- **Reproducible:** the genome class GO'd on 6/30 seeds (1,7,10,14,21,25), 3 of them golden — a
  consistent attractor, not a seed-hopping lottery.

**Full sweep:** GO 9/30; tiers 3 golden / 6 specialist; GO pairs BNB/ETH, BTC/ETH, BTC/SOL.

**Chunk-P verify ANSWERED (the gate held against the bigger surface):** the combo family was the
most-explored, but produced NO false golden — its lone GO (seed 6 BTC/ETH) was tagged specialist,
and its high-return thin-trade traps were correctly NO-GO'd (seed 17 +47%/11t, 26 +43%/13t, 27
+35%/10t — all caught by the 15-trade floor / fragility). The genuinely structural edge earned
golden while the bigger surface did NOT manufacture false positives. The judge discriminates
correctly under heavy load. XRP/USDC (B&H -64.6%) was a death trap — every winner on it NO-GO'd.

**Why golden appeared now vs 0 golden in the 50x20 run:** a bigger search (pop 300/80 gens)
reliably FINDS the BNB/ETH MR edge instead of getting trapped on BTC crash-shorts, and 30 seeds
gave the consistent signal enough repetitions for the cross-pair tagger to confirm it.

**Forward-tested through the LIVE path (2026-06-28):** drove the exact re-derived genome bar-by-bar
through `ForwardRunner` (decode + decode_portfolio perp + stop_pct) over the holdout as if polling
daily. Live == BacktestEngine == one-shot, per-bar equity IDENTICAL, return EXACTLY +29.0625% — so
the genome that graduated will trade identically in live forward execution incl. its short legs
(the `forward` CLI's spot-only STRATEGIES dict can't express it; ForwardRunner itself can). Trade
tape: 28 rotations / 134 bars, longs the Feb-Mar & Jun rallies and FLIPS SHORT through the Apr
drawdown (regime-adaptive leg working as designed), 50% stop never binds (too wide), max DD 27.6%.
BUT this replays the SAME holdout graduation scored — it proves live-path PARITY + shows behaviour,
it is NOT fresh out-of-sample (no post-holdout data exists yet; genuine OOS needs `forward --follow`
on new daily bars, or a stricter nested holdout the gate never touches).

**Caveats (candidate edge, NOT validated alpha):** BNB/ETH is the SHORTEST series (676 bars ->
134-bar holdout, 19 trades — decent but small-sample); `period=2` RSI is noisy; "decorrelated"
peers still share legs (BNB/ETH/XRP) in a 15-pair universe, so golden = held on 4 of 5
imperfectly-independent pairs. Next: forward-test this genome (chunk F), and scrape more bases so
cross-pair has truly independent peers. This is the first thing to survive EVERY filter the system
has AND generalize. See [[chunk-o-cross-pair-robustness]], [[chunk-p-bounded-combo]],
[[direction-regime-adaptive]] ([[direction-gene-overfits-regime]]), [[stop-loss-hurts-mean-reversion]]
(note: a 50% stop is wide enough to barely bind here), [[build-roadmap]] (chunk R will allocate to
golden vs specialist tiers).
