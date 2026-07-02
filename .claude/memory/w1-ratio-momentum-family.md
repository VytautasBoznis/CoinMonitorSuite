---
name: w1-ratio-momentum-family
description: "chunk W1: ratio_momentum family — first signal class out of the RSI valley; registration-only, whole pipeline consumes it unchanged"
metadata: 
  node_type: memory
  type: project
  originSessionId: 365aef7e-9ce8-449c-92e0-1bbda18d3823
---

Chunk W1 (2026-07-02): added `strategies/ratio_momentum.RatioMomentum` — long when
`roc(close, lookback, skip) > band`, flat otherwise — the EXACT probe-H1 logic (the pulse that
PASSED on current data: 5/8 series positive median OOS, 56% pooled folds). Bounded `deque`
buffer of `lookback+skip+1` closes = O(1)/bar (N1 discipline; the probe used an unbounded list).
On a ratio pair (`BASE_i/BASE_j`) this IS cross-coin relative momentum — the crypto effect with
documented persistence, the first family out of the RSI valley the alpha hunt was stuck in.

Registered as an ordinary `genome.FAMILIES["ratio_momentum"]` (lookback 5–120 int, skip 0–10
int, band 0.0–0.10). **Key point: registration was the ONLY wiring.** The GA samples
`family = rng.choice(list(FAMILIES))` and mutate/crossover iterate the param dict generically, so
the whole pipeline (GA, decode/decode_portfolio incl. RegimeAdaptive+perp, OOS fitness, graduation,
cross-pair O tagger, U certificate, V1 null) consumes it with zero GA/engine edits — the same seam
chunk P (indicator_combo) used. Not added to the CLI `STRATEGIES` dict (that's the `--strategy`
name path for the 3 original families; searchable families live only in `FAMILIES`).

`band` is a searchable gene, NOT computed from CostModel (unlike EMACrossover): a churny band=0
corner just scores poorly OOS, so the search finds its own cost hurdle. Single-threshold (long
if roc>band else flat), no hysteresis — matches the plan spec and the validated probe exactly;
did NOT add a ±band hold band (would deviate from what passed H1; never tune to pass).

289 tests green (+15), ruff clean. **The family makes the momentum effect REACHABLE; it does
NOT prove alpha** — the real read is a live `coinmon search` picking momentum + `certify`/nulls
judging it. See [[build-roadmap]] chunk W, [[alpha-definition-edge-certificate]], and the plan
`.claude/plans/alpha-hunt.md` §W1/§3-S2. Next W items: W3 funding_carry (needs T funding table,
reshaped as carry capture per H6), W4 donchian_breakout, W2 seasonality last (H2 FAILed).
