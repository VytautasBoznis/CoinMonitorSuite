---
name: prototype-reference
description: "What the bachelor's prototype in C:\\Dev\\CoinMonitor is and which patterns to reuse"
metadata: 
  node_type: memory
  type: reference
  originSessionId: e131e52b-f793-4311-b099-7424ca5213bc
---

The user's bachelor's prototype lives in `C:\Dev\CoinMonitor` — 3 repos, .NET Framework / C#:
- **CoinMonitor** — just a draw.io architecture diagram + README.
- **CoinMonitorService** — Windows data-plane service. Layered (Base/Core/Domain/Interfaces/RestClients/Business/ServiceHost). `MarketWatchManager` (abstract) → `CexMarketManager`/`PoloniexMarketManager` poll tickers, sanitize to a common `TickerFormattedDto`, store raw+sanitized in Elasticsearch (hand-rolled REST). "EcoIndex" managers = indicators (RSI/EMA/ForceIndex) recompute over a ~25min window. `MarketWatchServiceHolder` drives polling via `System.Threading.Timer`.
- **CoinMonitorAPI** — ASP.NET Web API control-plane (Unity DI). Stores users, their exchange key/secret pairs, watched `CoinModel`s. `CexManager` only does `GetLastPrice` (trading never implemented).

**Patterns worth carrying into CoinMonitorSuite:** per-exchange adapter + sanitize-to-common-DTO; data-plane vs control-plane split; pluggable indicator/strategy modules; config-driven intervals.

**Gaps vs the new vision (all greenfield):** only tickers not candles; no backtesting; no real trade execution; no options; no signal/opportunity logic; no UI (the "frontend" repo is a diagram); Elastic-by-hand storage; Cex.io/Poloniex are faded venues. See [[project-direction]].
