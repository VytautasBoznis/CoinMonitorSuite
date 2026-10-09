---
name: bybit-dropped-no-eu-leverage
description: "DECISION 2026-10-09: Bybit DROPPED as execution venue (global rejected the EU owner; Bybit EU is spot-only, 0 perps). Replacement LOCKED same day: HYPERLIQUID (on-chain perps, USDC, agent key trades but should not withdraw)."
metadata:
  node_type: memory
  type: project
  originSessionId: 10d75e64-7ec1-47f1-8d42-efb2578a0cda
  modified: 2026-10-09T17:57:54.816Z
---

2026-10-09: the owner tried to set up on Bybit and **Bybit global refused them** ("global said fuck you"),
so they would have to use **Bybit EU (bybit.eu)**. Claude checked Bybit EU's public v5 API the same day:
**0 linear contracts on mainnet, demo and testnet**. It is spot only (128 pairs, BTC/ETH/SOL vs USDC and EUR).
Owner's verdict: **"bybit was chosen explicitly for leverage, if no leverage no bybit"**. Bybit is out as
the EXECUTION venue.

**REPLACEMENT LOCKED 2026-10-09: Hyperliquid** (owner: "fuckit lets do it"). Chosen after the owner asked whether
they can withdraw. Docs checked: USDC deposits on Arbitrum/Ethereum/Base/Polygon; withdrawals go to an EVM address the
owner signs for with their own wallet, $1 fee, ~5 min. The bot trades with an approved API (agent) wallet. The docs say
API wallets are "only used to sign" but do NOT state outright that they cannot withdraw. **Pre-money test owed:** attempt
a withdrawal signed by the agent key on testnet and confirm it is rejected. No account/support desk: the owner's wallet
seed phrase IS the account.

**What this voids:** [[bybit-only-leverage-doctrine]] (its venue premise; the leverage-class reasoning can be
re-applied to the next venue), the Bybit parts of [[live-bot-dashboard-plan]] (USDC-perp universe check,
`coinmon-live` Bybit subaccount, DCP/TP-attach checks), and the venue line of [[cursed-100-eur-live-ladder]].
The owner had picked "Global, USDC perps" earlier that session; that answer is void too.

**What it does NOT void:** research data. Binance dumps stay the backtest source. The Bybit candle scraper
and the `allLiquidation` collector ([[bybit-liquidation-collector]]) are public data and still run. Note
that Bybit liquidations no longer measure the venue being traded.

**Requirement carried forward:** the next venue must give an **EU resident leveraged perps**. Check the
owner's account eligibility before building anything; public-API availability alone proved nothing here.
Bot-core design (PANIC/DRAIN, HALTED flag, fills ledger) is venue-agnostic and carries over unchanged.

**How to apply:** do not build Bybit order plumbing. Do not suggest Bybit EU spot as a fallback either; the
owner rejected no-leverage outright. The spot F8 ladder also fails its own R1 test at ~0.1% spot maker fees
(about +0.38%/event against a 0.6% bar).
