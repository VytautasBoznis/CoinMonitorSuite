---
name: train-usdt-certify-usdc
description: "Quote currency IS the train/test split: search/train ONLY on USDT (Bybit USDT + Binance USDT long history); USDC series stay pristine and are used ONLY at the final Edge-Certificate validation. Never let search touch USDC."
metadata: 
  node_type: memory
  type: project
  originSessionId: cc8b2997-71e4-4d25-8616-f5545e120e1e
---

2026-07-02. User decision during chunk T (data expansion), confirmed explicitly:

- **Train/search on USDT only** — the abundant, long-history, cross-venue data (Bybit USDT +
  Binance USDT back to ~2017). More bars, more regimes, cheaper N for the certificate.
- **USDC = pristine final holdout.** The USDC series (the *real tradable instrument* on Bybit,
  the only quote we ever trade — [[project-direction]]) is NEVER touched during search/GA/gate.
  It is used ONLY at the final Edge-Certificate validation ([[alpha-definition-edge-certificate]]).
- So the **quote currency itself is a train/test split**: the search never sees the instrument
  it will be certified (and eventually traded) on → a leakage-proof final exam on the real thing.
- This also authorized a **second venue**: Binance (backtest-history ONLY, never trades there),
  because its deep 2017+ history lives on USDT pairs. Bends the letter of the USDT-ban
  ([[project-direction]]) for DATA only; trading stays Bybit/USDC.

**Why:** every prior refutation rode on tiny single-quote holdouts; training on the deep USDT
universe buys the N the certificate needs, while reserving USDC as the untouched final gate makes
"passed" mean "generalized to the real instrument," not "curve-fit the only data we had."

**How to apply:** chunk U's `certify` and chunk Y's sweep must read USDT for search/pooling and
USDC ONLY for the final certificate validation. `discover_universe` for a SEARCH run should build
the USDT training universe; the USDC universe is reserved. Never wire USDC into GA/gate scoring.
