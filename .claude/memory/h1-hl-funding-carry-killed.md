---
name: h1-hl-funding-carry-killed
description: "H1 Hyperliquid-native funding carry KILLED 2026-10-20: the 2x isolated, daily-managed hedge died of 44 wick liquidations (-32.6%/yr). HL funding itself is real and NOT decayed (+13%/yr on hedged notional, last 12mo +11%, 3-9pp/yr above Binance). Post-hoc lead: portfolio margin. Plus HL data gotchas."
metadata:
  node_type: memory
  type: project
  originSessionId: 47066446-a89b-4c2b-b462-ade94313da72
  modified: 2026-10-20T19:07:12.848Z
---

Owner's pick 2026-10-20 ("dashboard stuff and then the HL stuff"). Probe `probes/h1_hl_funding_carry.py`, log
`runs/h1_hl_funding_carry.log`, first buggy run `_v1.log`. Caches `data/h1_hl_{funding,candles}.parquet`
(gitignored). Universe: the 11 HL perps with a same-asset HL USDC spot pair trading >=$100k/day
(HYPE, UBTC, UZEC, UETH, XMR1, ONEAR, USOL, UPUMP, PURR, UXPL, UENA). Window 2024-10-20 → 2026-10-20.

**Frozen book.** Long spot and short perp in equal quantity, perp 2x isolated, rebalanced at the daily
close once the price is 25% from entry. Liquidated when the day's perp HIGH reaches the liq price. Taker
fees. One equal-weight account.

**Verdict: KILL.** R1 -32.6%/yr, R2 last 365d -17.8%, R3 CI [-60, -20]%/yr, R4 7/11 coins positive.
- 44 liquidations; PURR alone had 35 (-97%/yr; max leverage 3x, so the 2x short liquidates at +28.6%).
  XPL -24%.
- Majors at 2x with no liquidation earn about 2/3 of their funding: BTC +5.1, ETH +4.9, HYPE +4.0,
  SOL +2.1%/yr. None clears 5%.

**What is true about HL funding (reusable facts):**
- **It pays more than Binance on every coin, same days:** BTC 7.7 vs 3.9, ETH 7.5 vs 3.4, SOL 3.0 vs
  -0.1, XPL 10.3 vs 6.6%/yr.
- It sits pinned at the 0.00125%/h baseline (11%/yr) 42-84% of hours.
- **NOTIONAL (yield on hedged notional, no margin) is +13.0%/yr on the account, last 365d +10.9%.**
  Unlike W3/F1/F3/F8/F9 on Binance/Bybit, the HL premium has NOT decayed in the recent year.
- W3's 30d-mean gate changes nothing (24 switches): HL funding is almost never negative for a month.

**Post-hoc leads (seen in the data; any retest needs its own pre-registration):**
- The kill is the margin structure, not the funding. Two things could capture the notional yield:
  HL **portfolio margin** (spot counting as collateral for the short), or intraday margin top-ups by a bot.
  Before designing that test, check HL's portfolio-margin eligibility, haircuts and the owner's account mode.
- Liquidating on the CLOSE (a mark-price proxy) still gives -5.4%/yr on the account; PURR is liquidated
  16 times even then.

**Data gotchas (HL info API):**
- **Spot troll prints at listing:** UBTC closed at 6.97M and 7.98M vs a ~96k perp in its first 10 days.
  Fix used: a coin goes live only after 7 consecutive daily closes within 2% of the perp.
- `spotMetaAndAssetCtxs`: match contexts to pairs by the ctx `coin` field, never by zip order.
- Spot pairs are named `@<index>` (UBTC = @142, HYPE = @107); PURR is `PURR/USDC`.
- candleSnapshot 1d serves the full history. fundingHistory returns 500 hourly rows per call.
- The whole pull (≈250 calls paced at 6s, ~25 min) caused no errors in the live bot.
- The `portfolio` endpoint is the account's burn history ([[live-bot-dashboard-plan]]).

Related: [[w3-carry-first-live-diagnosis]], [[f1-tail-gated-carry-result]], [[live-yield-hurdle]],
[[bybit-dropped-no-eu-leverage]].
