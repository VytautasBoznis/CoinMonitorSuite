---
name: hl-venue-limits-multibot
description: "Hyperliquid facts checked 2026-10-20 that gate multi-bot / carry / cross-venue work: fees, sub-account $100k-volume gate, per-address action limits, per-IP caps, portfolio-margin $10k gate, oracle = CEX weighted median every 3s"
metadata:
  node_type: memory
  type: reference
  originSessionId: b07cd4d1-531d-4981-a504-2599f052cef5
  modified: 2026-10-20T19:42:17.847Z
---

Checked against the official HL docs (hyperliquid.gitbook.io) on 2026-10-20.

- **Fees, tier 0:** perps taker 0.045% / maker 0.015%; spot taker 0.070% / maker 0.040%. B20 was priced
  with Binance SPOT fees (0.1% / 0.02% per side), so it needs re-pricing at these.
- **Sub-accounts need $100,000 cumulative trading volume** (then up to 10). The owner's account has about one
  round trip, so per-bot wallets = separate MASTER wallets, each funded and each approving its own agent key.
- **Action limits are per address; sub-accounts count as separate users.** 10k buffer, +1 per USDC traded,
  then 1 per 10s. A separate wallet per bot gets its own buffer.
- **Per-IP caps (shared by every bot on the cluster):** REST weight 1200/min, 10 websocket connections
  (30 new/min), 1000 WS subscriptions. Open orders 1000 by default. Past ~3 bots, one shared feed is required.
- **Portfolio margin:** account value >$10,000 (or >$5M weighted volume) and <$5M; collateral BTC 50% LTV,
  HYPE 65% LTV; no open positions or orders when enabling; liquidation is account-wide; sub-accounts stay
  separate. Carry (spot long + perp short) is explicitly supported. See [[h1-hl-funding-carry-killed]].
- **Oracle:** validators publish a weighted median of CEX SPOT mids every 3s (Binance 3, OKX 2, Bybit 2,
  Kraken/KuCoin/Gate/MEXC/HL 1). It is a component of the mark price used for margining, liquidations and
  TP/SL triggers. The docs don't give the exact mark formula. This is the structural channel by which a
  Binance crash reaches HL's liquidation engine ([[swarm-and-cross-market-ideas]]).
- The docs don't say where the HL API servers are located.
