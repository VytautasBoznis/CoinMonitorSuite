---
name: w4-donchian-breakout-family
description: "chunk W4: donchian_breakout family — Donchian channel entry + ATR trailing exit; registration-only, but the 5th family shifted the GA RNG and needed a brittle-test budget fix"
metadata: 
  node_type: memory
  type: project
  originSessionId: 37f14828-b259-406b-849d-5b04e1b50625
---

Chunk W4 (2026-07-02): added `strategies/donchian_breakout.DonchianBreakout` — a long/flat
stop-and-reverse channel family, mechanically distinct from the moving-average families.
**Enter** long when the close breaks above the highest high of the PRIOR `channel` bars
(the Donchian upper channel — read from the deque BEFORE appending this bar's high, so the
close is compared against history, never its own bar; a steady +1/bar ramp with high=close+1
never *strictly* breaks out, an easy smoke-test gotcha). **Exit** via an ATR-scaled chandelier
trailing stop: track the highest close since entry, go flat when `close < peak − exit_mult·ATR`
(reuses `StreamingATR`; the stop widens with volatility). Bounded `deque(maxlen=channel)` of
highs = constant work/bar — `max()` over a ≤100 fixed window doesn't grow with n, so it honors
N1 discipline (no monotonic-deque was warranted; that'd be speculative complexity).

Registered as an ordinary `genome.FAMILIES["donchian_breakout"]` (channel 5–100 int,
atr_period 5–40 int, exit_mult 0.5–6.0). Same [[w1-ratio-momentum-family]] seam:
**registration was the ONLY wiring** — GA sample/mutate/crossover, decode/decode_portfolio
(incl. RegimeAdaptive short side + perp), OOS fitness, graduation, cross-pair O tagger,
U certificate, V nulls all consume it unchanged (no GA/engine edits).

**Gotcha worth remembering:** adding the 5th searchable family shifted the GA's RNG stream
(`family = rng.choice(list(FAMILIES))`) and broke ONE brittle pre-existing test —
`test_evolve_improves_fitness_over_generations` (test_ga.py) asserts the GA climbs to the
XRP/ETH synthetic optimum, but at pop20/gens15 the diluted family-sampling no longer reached
that pair from seed 0. Fixed by raising THAT test's search budget to pop40/gens20 (converges on
all 8 probed seeds → robust to the family count), never by cherry-picking a lucky seed. **Every
future family addition risks tripping this same test** — bump budget/robustness, don't re-seed.

333 tests green (+16, mirrors the W1 test file), ruff clean. Engine smoke: enters on gap-up
breakouts, exits on the ATR trailing stop. **Family makes breakout REACHABLE; alpha unproven** —
the real read is a live `coinmon search`/`certify` picking it. See [[build-roadmap]] chunk W,
`.claude/plans/alpha-hunt.md` §W4. Remaining W: W3 funding_carry (needs T funding table, carry
capture per H6), W2 seasonality last (H2 FAILed).
