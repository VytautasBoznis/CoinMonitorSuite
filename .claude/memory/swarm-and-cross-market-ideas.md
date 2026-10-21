---
name: swarm-and-cross-market-ideas
description: "Owner ideas 2026-10-20 (swarm, cross-market cascades, multi-market runs), phase order A/B/C and owner decisions. Phase A KILLED both; phase B step 1 (paper venue + 3 paper bots, approved bar) BUILT 2026-10-21, not deployed; next = dashboard switcher + scoreboard"
metadata:
  node_type: memory
  type: project
  originSessionId: b07cd4d1-531d-4981-a504-2599f052cef5
  modified: 2026-10-21T17:49:15.273Z
---

Owner, 2026-10-20, added to the "what's next" plan:
1. **Swarm:** many bots and strategies running at once, each with its own wallet, all fed by one collector,
   shown in one dashboard, with a scoring system for what's winning and losing.
2. **Cross-market cascades:** if a coin crashes (or pumps) on one market, expect it broadly; prep for it on
   another market (separate wallets, minimal latency).
3. **Multi-market monitoring + strategy runs** inside the same swarm.

**Claude's framing (proposed, not yet agreed):**
- The swarm's real value is as the forward-test harness for the post-hoc leads waiting on forward data:
  F8 wide-TP/long-hold and the 30d-trend filter ([[f8-cascade-ladder-result]]), F4 cliff-only
  ([[f4-unlock-short-killed]]) and HL carry ([[h1-hl-funding-carry-killed]]). These run as PAPER bots.
- **Scoring trap:** ranking bots by live P&L and backing the leader is live best-of-N (the "best of 162 was
  luck" grave). Score each bot against its own pre-registered backtest, with N, a CI and a "too early" label.
  Promote only by rules written in advance.
- The data model is already partly multi-bot: `bot_trades.bot` and `bot_control.bot` exist. The runtime is
  F8-specific (`control.BOT = "f8-ladder"`, one wallet per process via env).
- Idea 2 history: B3 (Binance vs Bybit on 4h bars) and H4 (BTC leading alts by a day) are dead
  ([[plan-b-p1-results]]). Minute and second scale have never been tested. A latency race from the EU home
  cluster is lost by design. The reachable version is effects lasting seconds or longer, e.g. through HL's
  3s CEX-median oracle ([[hl-venue-limits-multibot]]), used to place F8 bids, not to race.
- Real-money execution stays HL-only (EU leverage, [[bybit-dropped-no-eu-leverage]]). Monitoring and paper
  runs can use any venue's public data.

**Proposed order:**
- **A:** B20 re-priced at HL fees, plus a 1m cross-coin contagion probe (both on data already in the DB).
- **B:** swarm v1: shared feed, then bot = strategy + wallet + live/paper, then a dashboard switcher and
  scoreboard.
- **C:** a sub-second cross-venue collector (Binance/Bybit/HL), started with the shared feed.

**PHASE A DONE 2026-10-21: both KILLED.**
- B24 killed B20: [[anomaly-hourofday-lead]].
- C1 killed minute-scale contagion: [[c1-cross-coin-contagion-killed]].
- So the swarm's first tenants are only F8 live plus F8's post-hoc variants on paper (wide TP/long hold,
  30d-trend filter).
- Proposed lean order for phase B:
  1. Bot identity + paper venue first; paper bots share F8's market reads.
  2. Then the dashboard switcher and scoreboard.
  3. Then the shared feed, built together with the phase-C collector.
- Phase C's sharpened question: do Binance or other coins lead HL by seconds in market-wide crashes, enough
  to pull F8's bid first?

**OWNER DECISIONS 2026-10-21:**
- Order agreed: A (B20 at HL fees + 1m cross-coin contagion) first, then the swarm.
- **Paper by default.** Every swarm bot runs simulated trades on live data. The owner gives it cash only after
  it clears a bar written down before it starts.
- **A unique HL wallet per live bot:** yes.
- **Portfolio-margin carry ($10k+): not now.** "Might in the future if this shit would be profitable." Do not
  build or probe it until the owner reopens it. A free paper tracker in the swarm is fine.

**PHASE B STEP 1 BUILT 2026-10-21 (code + tests; NOT deployed: the owner flips `swarm.enabled`).**
- Paper = `src/coinmon/live/paper.py` `PaperVenue`. It offers LadderBot the venue's calls, so paper bots run the
  live bot's exact code. Fills are settled on closed HL MAINNET 1m candles exactly like `f8_param_grid.simulate`.
  `tests/test_paper.py` proves trade-for-trade equality (F8: 38 trips, wide: 15; nets to 1e-12), and a planted
  lookahead mutant fails 3 tests.
- So the chain decomposes cleanly: backtest → paper (forward regime only) → live (execution: queue, post-only
  rejects, partials). The **f8-twin** paper bot measures that last gap against the live bot.
- One process `coinmon swarm run`, one shared `HLMarket`, ~120 IP weight/min for any number of bots. No key.
  Ledger venue `hyperliquid-paper`, ids `<name>@hyperliquid-paper`, paper bots start RUN
  (`Store(initial=RUN)`). Restart restores open rows and settles the missed candles.
- Tenants in `swarm.BOTS`: f8-twin (measurement, never promoted), f8-wide (1.5/2.0/240, the grid's train pick),
  f8-trend (F8 + bid only if prior close ≥ the 1h close 30d earlier).
- **Bar APPROVED by the owner 2026-10-21, before any first run:** judged ONCE, 6 months after the first run
  (once more at 12 months if N < 50, then retired). Pass = N ≥ 50 AND mean net CI (UTC-day bootstrap) ex-zero
  AND paper yield ≥ 5%/yr at 1x. A pass earns F8-sized micro-live in its own wallet.
  **On deploy, write the first-run date HERE** (the judging clock starts then).
- Smoke run on real mainnet data 2026-10-21: twin bids at ~-2.5%, wide at ~-1.5%. **f8-trend sits idle**: all 6
  coins are below their price 30 days ago. Owner: keep it anyway.
- **NEXT = step 2:** a dashboard bot switcher + scoreboard (each bot vs its own backtest: N, CI, "too early").
  The swarm deployment can go live before it.

DB note: the local Timescale is on port **5433**, so set
`COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon` (the default DSN in config.py is 5432,
where something else answers). Binance 1h majors end 2026-07-06; the Binance perp 1m data (6 F8 coins, no BNB)
ends 2026-09-30.
