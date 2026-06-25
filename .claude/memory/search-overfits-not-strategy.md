---
name: search-overfits-not-strategy
description: "Empirical — the param SEARCH is the overfitting risk, not the strategy; GA fitness must be OOS/walk-forward with instability + trade-count penalties"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5095ec5a-0d98-4250-8620-a95937224a08
---

A 48-point RSI grid search under rolling walk-forward (train 365 / test 180, ETH/BTC daily)
**overfit catastrophically**: −22.89% out-of-sample vs +12.24% for the *fixed* default params
on the same span. Tells: 6/7 folds chose distinct params, train returns +72%/+40% collapsing
to negative OOS, in-sample ceiling +19.4% vs −22.9% delivered forward (~42pp overfit gap). Root
cause: only ~13–17 trades per window, so each fold's "optimum" is set by 1–2 trades = noise.

**Why:** this is the concrete, measured form of the brief's "hand-picked params are overfitting
bait" — except the surprise is the direction. The fixed textbook params generalize fine; the
DANGER is the optimizer. The eval rig demonstrated that the *search itself* is the primary
overfitting risk, independent of the strategy.

**How to apply (this is a design constraint on the GA north star [[blackbox-evolutionary-vision]]):**
if a tiny grid overfits this hard, an evolutionary search with far more degrees of freedom will
be far worse unless validation is brutal. The GA fitness MUST be:
- out-of-sample / **purged walk-forward**, never in-sample return;
- penalized for **parameter instability** across folds;
- penalized for **low trade counts** (few trades → noise-dominated fitness).
Build the fitness function around this before scaling the search. Related:
[[daily-meanreversion-goes-positive]], [[fragility-stress-test]], [[user-quant-background]].
