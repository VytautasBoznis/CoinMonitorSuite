---
name: bybit-only-leverage-doctrine
description: "Mr Fable's Bybit-only + 20x-leverage doctrine (2026-07-31), plus the MiCA/USDC conflict it collides with: leverage caps per idea class, and why the tradable perp universe is far narrower than the doctrine assumes."
metadata: 
  node_type: memory
  type: project
  originSessionId: 3556b2d1-b192-4660-9a90-f12eef7652c4
  modified: 2026-07-31T20:41:27.930Z
---

Delivered 2026-07-31 in response to the user's "what if I'm Bybit only?" + "I'm not allergic to 20x
leverage" prompts. Amends [[fable-batch-10-probe-queue]] and [[cursed-100-eur-live-ladder]].

**Framing fix (already project policy, no change needed):** "Bybit only" is an EXECUTION constraint,
not a data constraint. Study on free Binance dumps (they retain delisted symbols; Bybit's
public.bybit.com dumps have unverified delisted retention), trade on Bybit. This is exactly
[[train-usdt-certify-usdc]] — Binance is already backtest-history-only. Consequence: NOT strict
single-venue-everything, so Polymarket (idea 5) and the free Deribit DVOL proxy (idea 9) both survive.

**Leverage doctrine — 20x is three different animals:**
- *Capital efficiency (OK):* hedged books, ideas 1 and 3. Run in **UTA cross-margin** so the spot leg
  collateralizes the perp short — a squeeze marks both legs together instead of liquidating one side
  of a flat position. **Cap effective leverage 5-8x**; basis blowouts mark against the pair temporarily
  and 20x leaves zero room. Leverage buys capital efficiency here, never more edge.
- *Self-sabotage (BANNED above 2-3x):* idea 8 ladder bids. The premise IS surviving the bottom of the
  wick; levered fills die if the cascade runs one more leg and you become the liquidation flow you
  were harvesting. **Hard cap 2-3x, non-negotiable, or delete the idea.**
- *Dominated moonshot (avoid):* naked directional perp. At 20x isolated, Bybit liquidates a long around
  **-4.5%** (MMR ~0.5% low BTC tier, worse on alts — tiers drift, pull current). Median daily high-low:
  BTC ~3%, mid-cap alts 5-8%, so 20x directional on an alt has **liquidation-by-wick as its modal
  outcome, thesis irrelevant**. Oct 10 2025: 30-80% wicks, ~$19B liquidated in a day.
- *Correct lottery instrument:* a far-OTM Bybit USDC option (BTC/ETH/SOL), 2-4 weeks out. Same max loss
  as the perp punt, but premium IS the max loss and no wick knocks you out before expiry. Spreads wide,
  books thin — flag — but at 100 EUR the shape is right.
- *Funding trap:* long a hot alt at 20x can cost 100-300%/yr on equity in funding — that is literally
  what idea 1 collects. **Never be the counterparty to your own best strategy.**
- If the mood demands the number 20 on the account: put it on the **short perp leg of the funding-carry
  pair inside UTA**. Leverage screenshot without buying the barrier.

**THE CONFLICT Fable did not know about (verify before acting):** this project has a hard
USDC-only / never-USDT constraint from EU MiCA delistings ([[project-direction]],
`src/coinmon/config.py:14-15`). Fable's Bybit delta assumes the USDT universe. If the constraint holds
on Bybit, the *tradable* set shrinks hard and the queue REORDERS: dated USDC futures (3), USDC options
(9), and BTC/ETH/SOL ladders (8) fit natively, while hot-alt carry (1), new-listing funding (6),
unlock-cliff small-cap shorts (4) and USDT-quoted depeg bids (10) lose most of their universe, since
Bybit lists those overwhelmingly as USDT perps. Data/research is unaffected either way.

**How to apply:** treat the caps as pre-registered risk limits, not suggestions; re-pin probe fee
constants to Bybit (perp maker 0.02% / taker 0.055% -> taker RT ~0.11%, not the Binance-flavored 0.2%
in idea 4's block; spot 0.1% base — verify, tiers rot). Doesn't touch [[live-yield-hurdle]].
