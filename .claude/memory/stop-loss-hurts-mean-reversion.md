---
name: stop-loss-hurts-mean-reversion
description: Empirical finding — a fixed stop-loss made the RSI mean-reversion strategy worse on ETH/BTC (return, profit factor, AND drawdown all worse)
metadata:
  type: project
---

Finding (2026-06-25, from the backtester): adding a 5% `StopLoss` overlay to `rsi_meanreversion` on ETH/BTC 1h made **every** metric worse — total return −6.0%→−9.7%, profit factor 0.86→0.78, and (counterintuitively) max drawdown −13.5%→−17.4%, win rate 62%→61%, same ~71 trades.

**Why (it's structural, not a tuning miss):** a fixed stop is antithetical to mean-reversion. The strategy's premise is "this dip reverts"; the stop sells *into* the dip at the local bottom — so you realize the loss AND miss the recovery the thesis was waiting for. Same trades, but the stopped ones exit lower (PF drops), and realized losses compound permanently down the equity curve (an unrealized dip recovers; a realized loss doesn't), which is how cutting losses paradoxically *deepens* the equity drawdown. Stops belong to **trend-following** (cut losers, ride winners), not mean-reversion (the loser is the signal to hold).

**How to apply:**
- Don't pair fixed stops with mean-reversion strategies. For the future GA/search ([[blackbox-evolutionary-vision]]), a stop-loss "gene" is wasted (likely harmful) on mean-reversion genomes — scope it to trend-following ones, or let fitness kill it, but don't assume "stop = safer."
- The `StopLoss` overlay itself is fine and correct (composable, no-lookahead) — the lesson is about *which strategies* it suits.
- Caveat: 5% was hand-picked; the *level* is a search parameter to set under walk-forward, never eyeballed into profitability (overfitting trap).
