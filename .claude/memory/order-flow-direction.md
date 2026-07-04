---
name: order-flow-direction
description: "Agreed next direction (2026-07-04) — order-flow/positioning features (taker volume delta, open interest, long/short ratio) instead of price-transform indicators"
metadata: 
  node_type: memory
  type: project
  originSessionId: 30f1a354-ad20-4354-8b53-10fcc9d1bd2f
---

As of 2026-07-04 the project direction is to replace exhausted price-transform strategy
families with order-flow / positioning signal sources:

- **Taker flow / CVD**: executed market buys vs sells per candle (aggressor side). Bybit
  klines do NOT carry taker-buy volume; options are aggregating Bybit public trade-tape
  downloads (data.bybit.com) or Binance klines which include taker buy volume natively.
- **Open interest history**: Bybit v5 REST endpoint; rising OI + rising price = new longs,
  rising price + falling OI = short covering. Candle-aligned, easy scraper addition next to
  the existing funding scraper.
- **Long/short account ratio**: contrarian crowd indicator, Bybit REST.
- **Funding rate**: already scraped and stored (`funding_rates` table, h6_funding probe).

Order *book* imbalance (resting L2 depth) was considered and rejected: signal horizon is
seconds-to-minutes, no historical L2 available without months of self-recording, spoofing
poisons it.

Agreed first step shape: a cheap hypothesis probe (like existing probes/h*.py) testing
whether 4h OI-change + taker-delta sign predicts next-bar direction on majors better than
chance, BEFORE any GA integration. Related: [[no-more-rsi-ema-permutations]].
