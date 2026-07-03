---
name: certified-sweep-calibrated-negative
description: first live certified sweeps (chunk Y payoff run) = decisive calibrated NEGATIVE — 0 CERTIFIED across 1d moderate/heavy + 4h; every t_exp negative; price-shape valley is empty at these costs
metadata: 
  node_type: memory
  type: project
  originSessionId: ed03b353-6dcf-4cab-9952-46fa9b5dea51
---

The chunk-Y payoff run finally EXECUTED live (2026-07-03, USDT-train quote, Docker DB up —
prior sessions only ever built the code and deferred the run; see [[build-roadmap]] Y). Three
sweeps, all `sweep --certify --cross-pair 5 --graduate-min-trades 15`, 1d + 4h:

| run | config | GO | best certificate |
|---|---|---|---|
| moderate 1d | 8 seeds ×100×50 | 1/8 | UNPROVEN t_exp −0.03 (ratio_momentum BCH/DYDX, N=145, win .448) |
| heavy 1d | 20 seeds ×300×80 | 2/20 | UNPROVEN t_exp −0.03 (rsi_mr BNB/DYDX N=133 win .639 BUT exp −0.0006) |
| 4h | 8 seeds ×100×50 | 4/8 | 3 REFUTED + 1 UNPROVEN (best REFUTED N=418 win .428) |

**Result: ZERO CERTIFIED. Every single t_exp is NEGATIVE.** The nulls (C4) never even had to
run — you only reach the multiple-comparisons question if raw expectancy is positive, and none
was. These families lose money per-trade after costs before we ask whether they beat random.

Three things the run proved (each a live confirmation of an alpha-hunt design bet):
1. **Scale doesn't manufacture alpha.** Tripling pop + doubling gens (heavy 1d) produced the
   same UNPROVEN-at-best as the moderate run. Confirms plan §4: the binding constraint was never
   optimizer power, it was evaluation honesty. Never grow GA budget to chase a result.
2. **The C3 vanity-metric trap is real and caught live.** Heavy-1d BNB/DYDX had a 63.9% win
   rate (Wilson 0.568, CLEARS the ≥0.50 C2 bar) and STILL lost money (expectancy −0.0006). Win
   rate alone is a vanity metric; the expectancy CI (C3) is what kills it.
3. **4h evidence-multiplication worked — and multiplied toward "no edge, provably."** Only at 4h
   did N reach ≥300 (the C1 floor), which gave the certificate the power to move past UNPROVEN to
   REFUTED. 3/4 GOs REFUTED, win rates 18–43%, fees the executioner (priced honestly by the
   net-of-cost ledger). MR/price-shape dies of fees exactly as predicted.

Every headline holdout return (+2601%, +1232%, +587%…) was a 0–3-trade fluke killed by the
15-trade floor / fragility, or a regime/pair artifact that dissolved in the pooled per-trade
ledger. ALL GOs were SPECIALIST (0 golden) — nothing generalized across decorrelated peers.

**This is the calibrated NEGATIVE outcome chunk Y defines (the publishable-grade one):
price-shape rules on daily/4h crypto carry no retail-reachable edge at these costs.** Per the
plan this REDIRECTS the project out of the RSI/price valley rather than burning more compute in
it → W3 funding-carry certify (needs its own path — market-neutral, won't win a return-ranked
graduation gate, so it never surfaced a GO here), W5 cross-sectional rotation, or Plan B
alt-data ([[plan-b-fallback-probes]]). Reinforces [[nested-holdout-refutes-golden]] and
[[search-overfits-not-strategy]]: the search finds artifacts, only the certificate is trusted —
and it just returned an honest no.

Caveats: certify used the USDT quote (single-process sweep = train+certify same quote); the
pristine-USDC re-cert ([[train-usdt-certify-usdc]]) is a separate step but won't flip a negative
expectancy. Runs saved under `runs/` (sweep_usdt_1d.log, sweep_usdt_1d_heavy.log,
sweep_usdt_4h.log + go_winners_*.json). `runs/` is gitignored-adjacent — not committed.
