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
- [daily-meanreversion-goes-positive](daily-meanreversion-goes-positive.md) — RSI MR positive on ETH/BTC daily (fixed params +12% OOS, PF 1.51) vs −6% on 1h; fee-domination confirmed; downtrend-flattered risk result; 1d data now in the DB
- [search-overfits-not-strategy](search-overfits-not-strategy.md) — the param SEARCH overfits (−23% OOS) while fixed params survive (+12%); GA fitness must be OOS/walk-forward with instability + trade-count penalties
- [chunk-a-findings](chunk-a-findings.md) — chunk A validation: pulse is pair-specific (XRP ratios survive fragility), pair must be a gene, and the fitness symmetric-std penalty wrongly rejects all-folds-positive genomes
- [chunk-c-search-loop](chunk-c-search-loop.md) — chunk C GA: pure seed-deterministic mechanics (search/ga.py) + runner that scores OOS and gates the winner with fragility as a post-filter; CLI `coinmon search`
- [chunk-d-graduation-gate](chunk-d-graduation-gate.md) — chunk D graduation gate: graduate() runs the GA winner on a never-searched holdout + full fragility → hard go/no-go with reasons; `search --holdout`
- [build-roadmap](build-roadmap.md) — the chunked plan to finish the project (one chunk ≈ one session); source of truth for what's next
- [session-build-loop](session-build-loop.md) — how each session runs: read memory → do next roadmap chunk → ask blockers → deliver a commit message
- [user-commits-themselves](user-commits-themselves.md) — never run git commit; hand over a commit message and stop
