---
name: alpha-definition-edge-certificate
description: "THE project definition of alpha (the user's '≥51%'): an Edge Certificate over a pooled OOS trade ledger — N≥300 trades, win rate ≥51% with Wilson 95% lower bound >0.50, expectancy bootstrap-CI >0, beats explicit nulls, ≥2 regimes — replacing single-holdout equity as the success criterion. Full plan: .claude/plans/alpha-hunt.md"
metadata:
  type: project
---

2026-07-02. The user asked for a way to find strategies with "at least 51%" and to DEFINE it.
Definition adopted (details + rationale in `.claude/plans/alpha-hunt.md`, chunks T–Y in
[[build-roadmap]]):

A frozen genome/ensemble holds an **Edge Certificate** iff over its pooled, strictly
out-of-sample trade ledger (trade = closed round-trip, success = net-of-cost return > 0):
- **C1** N ≥ 300 pooled OOS trades (pooled across decorrelated pairs × rolling-window holdouts —
  the ONLY way to reach significance: proving >50% at 95% confidence needs ~6,800 trades at an
  observed 51%, ~270 at 55%; the old 13–20-trade holdouts had a ~11pp noise floor);
- **C2** observed win rate ≥ 0.51 AND Wilson one-sided 95% lower bound > 0.50;
- **C3** per-trade expectancy > 0 with moving-block-bootstrap 95% CI excluding 0 (win rate alone
  is a vanity metric — the 62%-win/negative-expectancy MR trap);
- **C4** certificate score (expectancy t-stat) > 95th percentile of explicit nulls (random
  genomes, exposure-matched random entries, surrogate-data full-search reruns);
- **C5** positive expectancy in ≥ 2 disjoint time regimes (kills single-regime crash-shorts);
- **C6** fragility Monte-Carlo intact.

Verdicts: CERTIFIED / UNPROVEN (fails only C1) / REFUTED. The graduation gate is demoted to a
cheap in-loop pre-filter; nothing is called alpha, forward-tested with intent, or traded
without a certificate. Why: the judge was validated but every GO was a one-regime equity bet
([[nested-holdout-refutes-golden]]); the certificate measures per-decision edge instead.
Never tune anything to pass the certificate or nulls — they are the exam, not the training set.
