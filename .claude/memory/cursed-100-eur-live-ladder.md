---
name: cursed-100-eur-live-ladder
description: "The cursed 100 EUR (2026-07-31): user will burn it on a sketchy site otherwise, so it goes LIVE this week into idea-8 liquidation-cascade resting bid ladders on BTC/ETH/SOL perps, isolated margin."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4520e228-25b0-4c00-a3cd-6a323fb7630d
  modified: 2026-07-31T20:45:35.752Z
---

User, 2026-07-31: **"100 EUR is cursed either way — I'm gonna burn it, and I will be sad if none is
picked, because then I'm gonna 'invest it' into a random sketchy site and lose all of it."** That framing
is what produced [[fable-batch-10-probe-queue]]; a live-money pick was a required output, not optional.

**The call (Mr Fable's):** idea 8 — liquidation-cascade ladder bids. Live, this week.
- 100 EUR split into resting bid ladders **2-4% under mid on BTC/ETH/SOL perps**, isolated margin.
- **Leverage: owner overruled Fable's cap (2026-07-31, confirmed).** Fable's doctrine says hard cap
  2-3x, non-negotiable ([[bybit-only-leverage-doctrine]]). The risk was stated in full and the owner
  declined the limit for this book. **Their call on their pre-declared burn — do not re-impose the cap
  and do not re-litigate it in later sessions.** Log the leverage actually used next to the fill data,
  since it changes how the fills should be read.
- The concern, for the record (stated once, settled): ladder bids fill 2-4% under mid *during* a
  cascade; at 20x liquidation sits ~4.5% below entry, inside plausible wick depth (Oct 10 2025 printed
  30-80% wicks), and a forced liquidation makes the position part of the flow it meant to harvest.
- **Why the override is coherent anyway:** this book's deliverable is DATA, not PnL. A fill yields real
  queue position and real cascade depth *before* any liquidation, so the artifact survives at any
  leverage. Only the PnL objective dies — and this 100 EUR was pre-declared a burn.
- Leave them there. No babysitting, no signal, no engine.

**Ranked alternatives for the same 100 EUR** (Fable, honest order): (1) this ladder — most
data-productive burn, every fill is queue-position truth the sim structurally cannot produce;
(2) one far-OTM BTC or SOL **Bybit USDC call, 2-4 weeks out** — the correct "to the moon" instrument,
same lottery downside but it survives the wick and pays at expiry; (3) 20x directional perp — worst of
the three, same max loss as the option plus a 4.5% tripwire that Oct-10-style days exist to harvest.

**Why this beats the skin site:** every fill is data the rig **structurally cannot simulate** — real
queue position, real cascade depth. Even a total burn produces artifacts the collector-based version
needs ([[liquidation-cascade-fade]]). Downside capped at 100 EUR; upside is a wick harvest plus a
calibration dataset. If it never fills, nothing was lost but the skin-site story.

**Standing constraints this does NOT override:** the proxy backtest's fill-at-wick-low is an upper
bound, so this is licensed as micro-live/data-gathering only — it is not a deployment and not a
certificate ([[alpha-definition-edge-certificate]], [[live-yield-hurdle]]). Extends the ~$10 micro-live
authorization in [[mission-find-edge-ship-ui]] to 100 EUR for this specific book.
