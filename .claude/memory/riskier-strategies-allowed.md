---
name: riskier-strategies-allowed
description: "USER DIRECTIVE (2026-07-18): riskier strategies are now allowed — the deploy hurdle's DRAWDOWN/variance objection is relaxed. But the >=5%/yr forward-yield floor and scientific honesty (survivorship, overfitting, multiple-testing) are NOT relaxed. Removing risk-aversion does not manufacture edge where there is none."
metadata:
  node_type: memory
  type: feedback
  originSessionId: SESSION_2026_07_18
  modified: 2026-07-18T13:49:10.724Z
---

User, 2026-07-18, alongside "continue work, minimal prompting": **"Allowing to go to riskier
strategies as well."**

**What it changes:** the [[live-yield-hurdle]] had two implicit parts — (1) expected forward net yield
>= 5%/yr, and (2) acceptable risk (drawdown/variance/leverage). This directive relaxes part (2). High
maxDD, leverage, directional/short-gamma books, and lower-Sharpe strategies are now on the table if the
YIELD clears.

**What it does NOT change (verified in the same session):**
- The **>= 5%/yr forward yield floor** stands (part 1). Leveraging a thin edge does not help: carry at
  recent ~0.18%/yr is still sub-5% at any sane leverage; the problem is the premium, not risk appetite.
- **Scientific honesty stands.** Survivorship bias, overfitting, and multiple-testing are data/method
  problems, not risk-appetite problems. Relaxing risk-aversion does not rescue a strategy whose "edge"
  is a survivorship artifact (B14) or a cherry-picked config (B13 L=90 / B17 best cell).

**How to apply:** when a lead was shelved, check WHY. If it was shelved on drawdown/variance ALONE,
"riskier allowed" may revive it — re-test at the relaxed risk bar. If it was shelved on thin yield,
survivorship, regime-dependence, or overfitting, this directive does NOT revive it; say so and move on.

**First application (2026-07-18):** re-opened B14 (shelved on maxDD) — but the decomposition showed its
edge is survivorship-suspect + crash-timed, so it stays closed ([[b13-low-vol-fresh-lead]]). Then hunted
genuinely riskier NEW families: time-series-momentum/CTA (B17) and OI-positioning (B18/B19) —
[[session-2026-07-18-tsmom-oi]]. All negative; still 0 deployable winners. See
[[mission-find-edge-ship-ui]], [[autotrading-rollout]].
