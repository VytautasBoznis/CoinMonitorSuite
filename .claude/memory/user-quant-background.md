---
name: user-quant-background
description: "User has limited quant-math background; relies on tooling + search to find edge, not hand-derived strategies"
metadata:
  type: user
---

The user (self-described, 2026-06-24) has **little quant knowledge** and does not expect to hand-derive profitable trading math themselves. Their deliberate approach ("pocket sand"): build a rigorous black-box backtest + fragility evaluation rig and let **search/evolution** surface strategies, rather than authoring alpha by hand. See [[blackbox-evolutionary-vision]].

**How to apply:** when advising, don't assume quant fluency — explain trading/stats concepts plainly (e.g. cointegration, Sharpe, leg risk were all worth spelling out). Lean into building strong *evaluation/measurement/robustness* tooling (the thing they can control) over proposing sophisticated math they'd have to derive. Flag overfitting and false-edge traps proactively, since the search-driven approach is especially prone to them.

**Addendum (2026-07-03):** user openly enjoys gambling and self-describes as "lucky" at it — with
self-aware scare quotes; they know luck isn't edge (they refuted their own golden strategy). Treat
the gambling affinity as engagement fuel, not a risk signal — but when conversation turns to
sizing, deploying capital, or high-variance plays (Plan C especially), hold the standing frame the
user themselves endorsed: the RIG decides go/no-go and sizes (certificate + forward evidence),
"lucky" never gets a vote in position sizing, and any speculative bankroll must be inconsequential
at the TOTAL-allocation level. State it matter-of-factly, never paternalistically.

**Casino-wallet protocol (declared by the user in advance, 2026-07-03):** the user WILL make
occasional dopamine gambles (~$100 on a promising shitcoin), especially after stretches of
negative results — declared openly, so it is fenced business-as-usual, NOT an alarm or a
discipline breach. Agreed fence: a physically separate casino wallet with a fixed entertainment
budget, never refilled early after losses, P&L counts as evidence of nothing. **The rule that
matters is the WIN case:** winnings sweep OUT (to savings / future rig bankroll); the casino
wallet stays capped forever — a hit never escalates the stakes ("lucky" filing for voting rights
is the actual risk, not the $100). Optional running joke with real value: log dumb gambles tagged
`dopamine`, excluded from all evidence, as a long-run personal-luck dataset. If the user proposes
a dumb gamble, remind of the fence in one flat sentence and otherwise let them have their fun.
