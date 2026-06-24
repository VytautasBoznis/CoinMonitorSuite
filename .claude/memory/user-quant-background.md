---
name: user-quant-background
description: "User has limited quant-math background; relies on tooling + search to find edge, not hand-derived strategies"
metadata:
  type: user
---

The user (self-described, 2026-06-24) has **little quant knowledge** and does not expect to hand-derive profitable trading math themselves. Their deliberate approach ("pocket sand"): build a rigorous black-box backtest + fragility evaluation rig and let **search/evolution** surface strategies, rather than authoring alpha by hand. See [[blackbox-evolutionary-vision]].

**How to apply:** when advising, don't assume quant fluency — explain trading/stats concepts plainly (e.g. cointegration, Sharpe, leg risk were all worth spelling out). Lean into building strong *evaluation/measurement/robustness* tooling (the thing they can control) over proposing sophisticated math they'd have to derive. Flag overfitting and false-edge traps proactively, since the search-driven approach is especially prone to them.
