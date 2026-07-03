---
name: user-infra-ui-plans
description: "User-owned workstreams (2026-07-03): internal build pipeline + k8s cluster for 24/7 collectors, centralized DB (no partial data on random machines), a DB-stitch CLI for relocation gaps, a research UI (trade dots on price map + exit reasons) wanted early, memory-system extraction as a future separate project"
metadata:
  node_type: memory
  type: project
---

Stated 2026-07-03, all user-owned unless a chunk is explicitly requested:

- **Infra:** user will build an internal build pipeline + k8s cluster to host the 24/7
  collectors ([[plan-b-fallback-probes]] Z0). Hard requirement: **centralization** — no
  partially-collected data strung across random machines. Known future scenario: the main
  machine goes offline for relocation; interim collectors run elsewhere and a **CLI to
  "stitch" DB entries collected on separate machines** merges them afterwards. (Technical
  note: candles/funding/OI rows have natural unique keys `(exchange, symbol, timeframe?, ts)`,
  so stitching is an idempotent upsert-merge — design collectors so all new tables keep
  natural keys, no autoincrement identity that would break merges.) **Why:** relocation is
  planned; data continuity through it matters more than elegance. **How to apply:** don't
  build infra unasked; when collector tables are added, keep them merge-friendly.

- **UI:** full tiered plan now lives in [[ui-roadmap]] (research UI after first certify
  ledgers → forward-paper dashboard with chunk G → Phase-2 product UI last).

- **Memory system:** user likes this project's file-based memory and plans to EXTRACT it
  later as a plug-and-play context system for other projects — explicitly a separate future
  project, not part of CoinMonitorSuite. Don't start it unasked.
