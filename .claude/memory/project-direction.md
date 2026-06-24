---
name: project-direction
description: "CoinMonitorSuite goal, stack, exchange, instrument focus, and phased roadmap"
metadata: 
  node_type: memory
  type: project
  originSessionId: e131e52b-f793-4311-b099-7424ca5213bc
---

CoinMonitorSuite = greenfield crypto monitoring + automated trading tool. Successor to the user's bachelor's prototype in C:\Dev\CoinMonitor (see [[prototype-reference]]) — that prototype's *patterns* are reference only, not a foundation to port.

**Decisions (firm, from user 2026-06-24):**
- **Stack: Python** (greenfield). Chosen for the quant/backtest/exchange ecosystem and example volume; speed is irrelevant pre-profit, rewrite acceptable later. Engine pure Python; FastAPI for the control-plane API and React/TS for UI when those phases arrive.
- **Exchange: Bybit as the initial target, exchange-agnostic architecture.** Per-exchange adapter abstraction so more venues are cheap later; only Bybit is implemented now. `ccxt` for access.
- **Primary quote currency: USDC** (not USDT) — hard constraint: USDT is unavailable to the user in the EU (MiCA delistings), so USDT must never be reintroduced. Default base symbols are `*/USDC` (e.g. BTC/USDC).
- **Where the edge is expected: coin/coin (ratio) pairs, not fiat/stablecoin pegs.** User's thesis: USDC-quoted coins are dominated by beta to BTC (mostly trend), whereas a ratio like ETH/BTC strips that common beta and is more mean-reverting → better ground for the strategies. Implementation: synthesize ratios from two USDC series (ETH/BTC = ETH-USDC ÷ BTC-USDC); a synthetic ratio is "just another OHLCV series" so it feeds the existing engine/strategies unchanged. Spot only allows *rotation* (hold A or B); true market-neutral long-A/short-B pairs trading needs perps (later).
- **Spine = trade coins efficiently, NOT an options play.** Full options was rejected as too extreme on top of crypto volatility. Bybit options (puts/calls) stay *available* but are not the focus — so we only need candles, not a historical vol surface.
- **Instrument: spot (long/flat) for Phase 1** (confirmed 2026-06-24). Simplest honest baseline, no funding data needed. Perps are a later `PerpPortfolio` impl behind the same `Portfolio` interface (long/short + 8h funding). Spot and perp prices move in lockstep — same candles → same signal, so it's not a lead/lag edge; genuine derivatives signals (funding rate, OI, long/short ratio) are a Phase 2 candidate needing feeds beyond candles. See [[phase-1-backtester]].
- **Phased roadmap:** Phase 1 = backtesting → Phase 2 = generate trade suggestions → Phase 3 = full automation. One Strategy interface flows through all three.

**Why:** these reframe the whole build — the hard options-data problem is off the table, scope is single-exchange candle-based, and execution risk is deferred behind a backtest-first sequence.

**How to apply:** default new work to Python + Bybit + candle-based; don't reintroduce options-first assumptions or multi-exchange complexity before Bybit Phase 1 works.
