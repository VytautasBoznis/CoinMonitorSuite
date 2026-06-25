---
name: fragility-stress-test
description: "Monte Carlo latency/slippage stress test as a kill-filter for thin-margin strategies"
metadata:
  type: project
---

The backtester must include an **optional fragility stress test** (user request 2026-06-24): an `ExecutionModel` seam in the engine with a `StochasticExecution` impl exposing seedable knobs for **latency** (signal→fill delay), **slippage** (adverse bps), and **fill failure** (miss/partial). A Monte Carlo runner replays a strategy N times and reports a distribution + sensitivity sweep, yielding a **fragility metric** (e.g. "% of runs still beating buy-and-hold") to detect strategies whose margin is too thin to risk live.

**Why:** the developer wants to reject too-risky strategies *before* live trading, simulating real-world network/execution imperfection as far as theory allows.

**Status — BUILT (2026-06-25):** `StochasticExecution` + `MonteCarloResult` + `run_monte_carlo` in `backtest/stress.py`; opt-in via `coinmon backtest --stress N` (default 0 = off). The `ExecutionModel` seam was widened to `fill_price(side, reference) -> float | None`: `side` lets slippage be applied *adversely* (buy fills higher, sell lower), `None` = the order didn't fill (engine leaves position unchanged; strategy re-issues next bar). Latency+spread+impact are collapsed into one adverse `uniform(0, max_slippage)` draw ("modeled once"). Seeding is per-run via `SeedSequence(seed).spawn(runs)` so it's reproducible. `run_monte_carlo` takes strategy+portfolio **factories** (both are stateful → fresh per run).

**Deliberately deferred — the inter-leg gap.** The brief lists "inter-leg gap" as a 4th knob, but the engine models the synthetic ratio as ONE instrument rebalanced at a single price (not two sequential ETH/USDC + BTC/USDC orders). So the two-leg drift can't be expressed at the current seam — it needs the engine to actually model the rotation as two orders (the "sequential non-atomic legs" of [[blackbox-evolutionary-vision]]). Adverse slippage approximates "you don't get the clean price" for now; explicit leg modeling is a separate, larger change.

**How to apply:**
- Off by default; the baseline backtest stays deterministic and clean (`IdealExecution` = next-bar open, no slippage, always fills).
- It's a **kill filter, not a validation badge** — failing = red flag, passing ≠ live-ready. Never tune params to pass it (overfits the noise model).
- In a historical backtest, "data lag" and "execution lag" are the **same** mechanism (acting later on stale, worse-known prices) — model once, not twice.
- Related hard requirement: spot rotations charge **both** taker legs (sell A→USDC, buy USDC→B); fees dominate mean-reversion edges. See [[project-direction]].
