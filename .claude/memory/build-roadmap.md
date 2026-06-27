---
name: build-roadmap
description: "The chunked plan to finish CoinMonitorSuite — one chunk ≈ one session; source of truth for what's next"
metadata: 
  node_type: memory
  type: project
  originSessionId: d2b51f14-af0b-4701-8a48-a061e92ae8ba
---

The plan to take CoinMonitorSuite from "validated backtester" to "deployable
search→suggest→automate system." Ordered by dependency and the discipline from
[[search-overfits-not-strategy]]: **validate before scaling, search before suggesting,
suggest before any live execution.** Worked one chunk per session — see [[session-build-loop]].
Tick chunks `[x]` as done and add a one-line result. Each chunk ends with a commit message
(user commits — [[user-commits-themselves]]).

**Definition of done for the project:** a Dockerized, k8s-deployable system that backtests +
honestly validates strategies, runs an evolutionary search gated by OOS/walk-forward +
fragility, graduates a survivor through an untouched holdout, emits live trade suggestions, and
(opt-in, safety-gated) auto-executes spot rotations on Bybit.

## Already done (pre-roadmap)
- Phase 1 backtester (black-box engine, SpotPortfolio, metrics) + Phase 1.5 fragility harness.
- Scraper + Streamlit viewer, both Dockerized, writing TimescaleDB ([[backtester-reads-timescaledb]]).
- Walk-forward + **purged** embargo + **OOS fitness function** (`backtest/fitness.py`,
  `evaluate_fitness`) — the GA's scoring substrate. (2026-06-28)

## Chunks (in order)

- [ ] **A — Real-data validation run.** DB up (needs user to start Docker). Run purged
  walk-forward + `evaluate_fitness` on ETH/BTC daily; add 2–3 more ratio pairs + a
  non-downtrend window. Verdict: is there a pulse worth scaling? Write a findings memory.
  *Blocked on: Docker up; which pairs/backfill range.* Verify: numbers reproduced, doc updated.

- [ ] **B — Genome representation.** A `Genome` (param vector) ↔ Strategy decode + a registry of
  strategy families with param ranges, so `evaluate_fitness` can score any genome. Verify: round-trip
  decode tests; existing RSI/EMA expressible as genomes.

- [ ] **C — Evolutionary search loop.** GA over genomes: population, selection, crossover,
  mutation, generations; fitness = `evaluate_fitness` (OOS + penalties), **fragility as a gate**
  (post-filter or into fitness). CLI `coinmon search`. Verify: GA improves fitness on a seed; a
  deliberately-overfit genome is rejected by OOS/fragility (the brief's "reject garbage" proof).

- [ ] **D — Graduation gate.** Pipeline that takes the GA winner, runs it on a never-touched final
  holdout span + full fragility kill-filter, emits a go/no-go report. Verify: garbage genome fails
  the gate; the gate is the only path to "live-eligible."

- [ ] **E — Indicator/feature-store engine (conditional).** Only if the GA is compute-bound:
  precompute fixed-menu indicators to DB, serve `BarView.features` point-in-time ([[feature-store-seam]]),
  strategies take the fast path. Own Docker container. Verify: identical results vs recompute, big speedup.

- [ ] **F — Live forward feed.** Run a graduated strategy forward in real time off the scraper's
  growing DB (live BarView), same engine contract. Verify: forward replay matches backtest on
  overlapping bars (parity).

- [ ] **G — Phase 2: suggestions service.** Service runs the graduated strategy live (paper) and
  emits trade suggestions; no execution. Dockerized; FastAPI control-plane begins.
  *Blocked on: how suggestions are delivered (log/webhook/Telegram/UI).* Verify: emits a correct
  rotate signal on a known historical replay.

- [ ] **H — Control-plane API + minimal UI.** FastAPI (strategies, results, suggestions, search
  runs) + minimal React/TS UI. Dockerized. Verify: endpoints return live state; UI renders it.

- [ ] **I — Phase 3: automated execution.** Bybit order path behind the ExchangeAdapter order API
  (same contract as the sim), sequential two-leg rotation with real gap. Testnet/paper first, then
  tiny live. Safety: dry-run default, kill switch, position/loss limits. *Blocked on: testnet vs
  live, capital cap — ASK, high risk.* Verify: testnet round-trip rotation executes + reconciles.

- [ ] **J — k8s packaging.** Dockerfiles for every component (engine/search/API/executor),
  Helm chart or manifests, ConfigMaps + Secrets for API keys ([[deployment-target-k8s]]).
  Verify: `helm template`/manifests apply clean; a component runs in-cluster.

## Notes
- **Money safety (hard line the user cares about):** chunks A–H and J place **no orders and risk
  no money** — they only read data and simulate (F/G use read-only public market data, no keys).
  **Chunk I is the only place real money can enter**, and it defaults to dry-run → testnet → tiny
  live, gated behind explicit user opt-in + capital cap. Trade-permission API keys do not exist in
  the system until I, so nothing before it can physically trade.
- Chunks A and the analysis chunks need the user to start Docker Desktop (DB on host port 5433;
  set `COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon`).
- Re-scope freely as findings land (e.g. if chunk A shows no pulse, the GA chunks pivot to
  proving the rig rejects garbage rather than chasing alpha). Keep this list honest.
