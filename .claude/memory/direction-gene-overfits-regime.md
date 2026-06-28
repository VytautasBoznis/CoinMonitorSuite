---
name: direction-gene-overfits-regime
description: "The binding cause of every live graduation NO-GO: the free direction gene (short on/off, chunk K) is fit to the search span but blind to the holdout regime, so the GA bets the wrong direction — long where the holdout crashes, short where it rises. The gate itself is passable; direction is the overfit vector. Fix = regime-adaptive strategy, not a coin-flip direction gene."
metadata:
  node_type: memory
  type: project
  originSessionId: continue-2026-06-28
---

**Finding from the gate-passability sweep, 2026-06-28** (see [[chunk-l-live-validation]] for the run
details). After chunk L killed the reckless-leverage attractor, EVERY remaining live graduation NO-GO
traced to one thing: **the direction gene (`short` on/off + `leverage`, chunk K2) is selected on
search-span fitness, which carries no information about which way the unseen holdout regime breaks.**

**The proof.** Same genome, two directions, on BNB/ETH's +13.65% holdout:
- `rsi_meanreversion BNB/ETH` **as 1x perp short** (what the GA actually picked) → holdout **-0.92%**,
  fragility 2% → **NO-GO**. It shorted an UP regime.
- the SAME `rsi_meanreversion BNB/ETH` params **as long/flat spot** → holdout **+8.50%**, 14 trades,
  100% fragility → **GO**.
The parameters were fine; only the direction bet was wrong. Mirror image on ETH/USDC: the GA picked LONG
(best on a net-up search span), the holdout was a -57% crash → NO-GO. So the GA reliably bets the
direction that won in-sample, and the holdout's direction is independent of that.

**Why this is the binding issue and not the gate.** The gate is PASSABLE (the long twin GOs), so it is
not too strict and does not need redesign. Direction is simply the most regime-sensitive gene, and a
walk-forward search cannot select it from past data when the future regime is independent. A coin-flip
`short` gene locked in by in-sample fitness is therefore an overfit vector — the same lesson as
[[search-overfits-not-strategy]], now with DIRECTION as the thing that overfits.

**Implication for the roadmap.** Chunk K (perp short as a free direction gene) gave the bot the
*capability* to short, but making direction a free GENE optimized in-sample is the wrong control surface.
The promising fix is a **regime-adaptive representation**: a strategy that goes long on bullish signals
and short on bearish ones (signal-driven, flips with the regime) so the same genome adapts instead of
betting one direction persists — NOT `ShortWhenFlat` (a crude always-on flip of the exit) and NOT a
fixed per-genome direction. Alternatives if adaptivity is too big a step: drop `short` back out of the
gene set (long/flat only, accept that down-regime holdouts will NO-GO honestly), or score genomes across
BOTH an up-fold and a down-fold so direction-betting is penalized. Decision pending with the user.

Caveat worth remembering: a regime-adaptive strategy is NOT guaranteed to pass either — on ETH/USDC's
*choppy* crash, trend-following SHORTS lost MORE than the long that sidestepped ([[chunk-l-live-validation]]),
so "adapt to short in a downtrend" only helps in a clean trend, not a whipsaw. Validate, don't assume.

**UPDATE 2026-06-28 — regime-adaptive strategy IMPLEMENTED (chunk M, see [[build-roadmap]]).** Decided
with the user: REPLACE the fixed `short: bool` gene with `direction ∈ {"long","adaptive"}` (the overfit
vector is gone, not merely reachable), and make the regime window a searchable gene. New
`strategies/directional.RegimeAdaptive(base, trend_period)`: reads a point-in-time SMA of the closes it
has seen; up-regime (close ≥ SMA) runs the base long/flat unchanged (so it will NOT short a rising
holdout — the BNB/ETH fix), down-regime (close < SMA) applies `ShortWhenFlat` (short the would-be-flat
legs — rides a falling holdout). It reuses the SAME `ShortWhenFlat` instance for the down branch and calls
the base exactly once per bar (no double-consume). `Genome` gained `direction`/`trend_period` (TREND =
ParamSpec(20,200), inert when long); `decode` wraps in RegimeAdaptive + perp book; GA samples/mutates/
crosses + `_key` carries them; summaries read "Lx perp regime-adaptive (MA…)". Threaded byte-unchanged for
`direction="long"` (default = chunk-B spot, parity). 131 tests green (+4), ruff clean. Unit proof:
up-regime never shorts, down-regime shorts the flats; synthetic-downtrend graduation GO. **The real test
is the next user run** (`coinmon search --timeframe 1d --holdout 0.2 --stress 80`): does direction now read
the holdout's own regime and graduate GO where the fixed gene NO-GO'd? The choppy-crash caveat above still
stands — validate, don't assume.
