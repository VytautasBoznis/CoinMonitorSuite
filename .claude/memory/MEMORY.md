# CoinMonitorSuite Project Memory

This file indexes all memory files for the CoinMonitorSuite project.

## Files

- [project-direction](project-direction.md) — Python/Bybit greenfield, trade-coins-efficiently (not options-first), phased backtest→suggestions→automation
- [prototype-reference](prototype-reference.md) — the .NET bachelor's prototype in C:\Dev\CoinMonitor; which patterns to reuse vs the gaps
- [fragility-stress-test](fragility-stress-test.md) — Monte Carlo latency/slippage stress test as a kill-filter for thin-margin strategies before live
- [blackbox-evolutionary-vision](blackbox-evolutionary-vision.md) — north star: engine = live-compatible black-box exchange; sequential non-atomic legs; evolutionary/GA search is the long-term path to alpha
- [user-quant-background](user-quant-background.md) — user has limited quant math; relies on the eval rig + search, not hand-derived strategies
- [deployment-target-k8s](deployment-target-k8s.md) — runs in a Kubernetes cluster; every component must ship as a Docker image; config via env/ConfigMaps
- [feature-store-seam](feature-store-seam.md) — BarView point-in-time feature-snapshot contract; future post-scraper indicator engine (compute-sharing for many bots), kept as cache not contract; engine itself deferred
- [backtester-reads-timescaledb](backtester-reads-timescaledb.md) — backtester loads candles from TimescaleDB (db.read_candles), not Parquet; store.py/fetch-data retired (brief said Parquet, reality is the scraper's Timescale)
- [stop-loss-hurts-mean-reversion](stop-loss-hurts-mean-reversion.md) — empirical: fixed stop-loss made RSI mean-reversion worse on every metric (stops suit trend, not mean-reversion); scope stop-loss genes away from MR in the GA
