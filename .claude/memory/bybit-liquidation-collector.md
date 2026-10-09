---
name: bybit-liquidation-collector
description: "Bybit allLiquidation collector BUILT and RUNNING since 2026-10-08 (local docker compose service `liquidations`, local Timescale): all ~859 linear perps, coverage-tracked. Non-obvious facts: Buy = long liquidated (verified), one bad topic poisons a subscribe batch, aiodns breaks on Windows. Does NOT settle queue position by itself."
metadata:
  node_type: memory
  type: project
  originSessionId: f6bf275c-ead1-4b47-92c8-46a8f51a8a71
  modified: 2026-10-09T17:29:04.316Z
---

Built 2026-10-08 as the NEXT of [[f8-cascade-ladder-result]] (idea 8 of [[fable-batch-10-probe-queue]]).
Code `src/coinmon/scraper/liquidations.py`, run `python -m coinmon.scraper.liquidations`; compose
service `liquidations` reuses the scraper image (`restart: unless-stopped`). Tables `liquidations`
(natural key) + `liquidation_coverage` (per-symbol `[start_ms, end_ms]` spans).

**RUNNING since 2026-10-08 ~17:38 UTC on the main machine's local docker → local Timescale (5433).**
When the k8s/central DB exists ([[user-infra-ui-plans]]), move it there and stitch: prints dedupe on
the natural key, coverage = union of spans. Stop: `docker compose stop liquidations`.

**Facts verified live (not in Bybit docs or contradicting intuition):**
- **`side='Buy'` = a LONG was liquidated = forced SELLING** (the flow ladder bids harvest). First 56
  prints: 8/8 Buy had bankruptcy price < 1m close; 44/48 Sell above (4 = intra-minute drift in a squeeze).
- **One invalid topic fails its whole subscribe batch** (other topics in it are NOT subscribed) →
  collector subscribes one topic per request; 199/199 single subscribes acked on one connection.
- aiohttp's default aiodns resolver fails on this Windows box ("Could not contact DNS servers") →
  `aiohttp.ThreadedResolver`. Git Bash `timeout -s INT` can't signal a native Windows python; test
  graceful shutdown in the container (SIGTERM path verified there).
- Push lag (recv − T): median ~0.9s, max ~1.1s. Rate in a quiet hour: ~1 print / 4s across all perps.

**OUTAGE 2026-10-08 19:24 → 2026-10-09 17:26 UTC (~22h).** The machine most likely slept. Docker
came back with Timescale exited (255), and `timescaledb` has NO `restart:` policy in compose, so the
collector crash-looped on DNS. Claude restarted the DB on 2026-10-09 and the collector recovered.
Before the outage it had only ~2h of data (1,315 prints). Coverage spans correctly exclude the hole.
Fix proposed, NOT applied: add `restart: unless-stopped` to timescaledb, and stop the box sleeping.

**Read coverage, never prints alone:** an empty minute means "no liquidations" only inside a span.
Crash semantics verified: coverage end stays ≤ last flush, so spans never claim lost prints.

**Honest scope:** this feed measures forced-flow size/timing per cascade; it does NOT settle queue
position. What settles the venue half of that question retroactively is re-running F8 on **Bybit's
own 1m perp klines** (REST serves 1m back to 2021-01 for BTCUSDT, listing date for newer perps) —
a Bybit print below your bid = guaranteed fill on Bybit. The exact-touch remainder needs the live book.
