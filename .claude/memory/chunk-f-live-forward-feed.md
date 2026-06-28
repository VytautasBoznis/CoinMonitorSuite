---
name: chunk-f-live-forward-feed
description: "Chunk F built the live forward feed: a shared BarStepper execution core + coinmon/live (LiveFeed, ForwardRunner) so forward replay reproduces the backtest exactly (parity)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8a2fce32-6ba0-4032-8b1c-20285619c5ed
---

Chunk F (2026-06-28) — the live forward feed, per [[build-roadmap]]. Runs a strategy forward off
the scraper's growing DB with the SAME engine contract; the verify-bar is **parity** (forward
replay == backtest on overlapping bars).

**Key design decision — parity by construction, not by duplication.** Rather than re-implement the
bar loop in a live runner and hope it matches, I extracted the engine's per-bar state machine into
a shared `BarStepper` + `StepResult` in `backtest/engine.py` (the fill→mark→decide core: fill last
bar's order at this bar's open, mark equity at close, ask the strategy for the next target).
`BacktestEngine.run` was refactored to use it (behavior-preserving — the 13 engine tests still
pass), and the live feed uses the same class. So backtest and live CANNOT diverge. This touched
working engine code, justified because "same engine contract" IS chunk F's point and the tests
guard it. `StepResult(open_time, close, filled, position, target, equity)`: `target` = position the
strategy now wants (fills NEXT bar, so the last bar's target never trades); `position` = held after
this bar's fill.

**`coinmon/live/`:**
- `feed.py` — `LiveFeed(read, pair)`: `poll()` re-resolves the pair each call (USDC-direct or
  synthetic ratio via `load_candles`) and returns only bars past an internal `open_time`
  watermark, so a strategy is driven exactly once per closed bar across many polls. No partial-bar
  guard needed: the scraper only ever stores CLOSED bars. Plus `frame_to_candles(frame)` helper.
- `runner.py` — `ForwardRunner(strategy, portfolio)`: wraps `BarStepper`, `feed(candles)` steps a
  poll's batch and accumulates `self.signals`; `latest` is the newest `StepResult`. State persists
  across polls (the batch-invariance property).

**CLI:** `coinmon forward --strategy {ema_crossover,rsi_meanreversion} --symbol --timeframe
[--follow --interval SECONDS]`. Default = one-shot replay of all stored bars (prints rotation log +
current holding/target/equity); `--follow` polls the DB and prints rotations as new bars close.
Read-only, no orders, no keys (money-safe per the roadmap).

**Status:** 94 tests green (`tests/test_live.py`). Parity proven two ways — scripted targets and
RSIMeanReversion on a sharply-oscillating sine (period=5, so it actually round-trips): forward
equity curve AND trade list equal `BacktestEngine`. Batch-invariance proven (multi-poll incl. an
empty poll == one-shot). **Limitation:** the CLI builds the strategy from the `STRATEGIES` dict,
not a graduated `Genome` — there's no persistence of graduated genomes yet; that wiring lands with
chunk G/H. Next: chunk G (Phase 2 suggestions service) — **blocked on the delivery channel**
(log / webhook / Telegram / UI), an intermission question for the user.
