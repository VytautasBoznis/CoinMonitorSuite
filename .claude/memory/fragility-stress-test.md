---
name: fragility-stress-test
description: "Monte Carlo latency/slippage stress test as a kill-filter for thin-margin strategies"
metadata:
  type: project
---

The backtester must include an **optional fragility stress test** (user request 2026-06-24): an `ExecutionModel` seam in the engine with a `StochasticExecution` impl exposing seedable knobs for **latency** (signal→fill delay), **slippage** (adverse bps), and **fill failure** (miss/partial). A Monte Carlo runner replays a strategy N times and reports a distribution + sensitivity sweep, yielding a **fragility metric** (e.g. "% of runs still beating buy-and-hold") to detect strategies whose margin is too thin to risk live.

**Why:** the developer wants to reject too-risky strategies *before* live trading, simulating real-world network/execution imperfection as far as theory allows.

**How to apply:**
- Off by default; the baseline backtest ([[phase-1-backtester]]) stays deterministic and clean (`IdealExecution` = next-bar open, no slippage).
- It's a **kill filter, not a validation badge** — failing = red flag, passing ≠ live-ready. Never tune params to pass it (overfits the noise model).
- In a historical backtest, "data lag" and "execution lag" are the **same** mechanism (acting later on stale, worse-known prices) — model once, not twice.
- Related hard requirement: spot rotations charge **both** taker legs (sell A→USDC, buy USDC→B); fees dominate mean-reversion edges. See [[project-direction]].
