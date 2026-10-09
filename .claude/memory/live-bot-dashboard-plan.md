---
name: live-bot-dashboard-plan
description: "DIRECTIVE 2026-10-09: owner LIFTED the >=3-winner UI gate for a live-bot inspection dashboard (bot + UI built together). No manual trade button; two manual STOP modes (PANIC now / DRAIN planned). Agreed build order + pre-money safety rules from the Fable conversation."
metadata:
  node_type: memory
  type: project
  originSessionId: f655be08-d28b-48b8-91b6-b4b28bbce97c
  modified: 2026-10-09T20:52:35.394Z
---

Owner, in a 2026-10-09 conversation with Fable (pasted into Claude Code): a bot running headless on the
cluster is "literally just a scam for myself": money goes in and disappears with only a log entry.
They want to SEE it, and to be entertained by it. Fable agreed and stated the lift: **"UI gate lifted by you"**.
**Scope of the lift:** the live-bot monitoring dashboard only. The Phase-2 scanner/product UI in
[[ui-roadmap]] stays gated. Real-capital rules are unchanged: [[live-yield-hurdle]] and [[cursed-100-eur-live-ladder]].

**Owner requirements (theirs, not suggestions):**
- **No manual trade button.** They do not want to place trades from the UI.
- **Manual STOP, two modes.** PANIC means "drop everything NOW, flatten, liquidate". DRAIN is for
  planned downtime (e.g. a hardware upgrade): no new risk, exit when possible, then a browser alert when flat.

**Agreed design (Fable):**
- Two CLI commands, `coinmon stop --now` and `coinmon stop --drain --deadline 90m`; the UI buttons call
  the same code. PANIC runs as a standalone script that needs only the API key and a Bybit client, never the
  bot. The persisted HALTED flag survives restarts, so the bot comes back idle until Resume. Flatness is
  confirmed by re-querying Bybit, never from the bot's own state. Default DRAIN deadline: 90m (F8 max hold is 60m).
- The UI reads only from the DB. Its only writes are pause/kill rows in a commands table. The bot never depends on the UI.
- Five screens: (1) cascade view, (2) burn meter, (3) fills ledger with backtest assumption vs actual,
  (4) bot health with PANIC (hold 1s) and DRAIN buttons, (5) scoreboard + graveyard.
- Pre-money: a dedicated Bybit subaccount `coinmon-live` with a trade-only, IP-whitelisted key and no
  withdrawal permission (the hard loss cap); take-profit placed exchange-side at fill; a heartbeat alert.
- Order: F11 probe → bot core → F8 ladder live on 100 EUR → F1 in paper mode → UI screens as data appears.

**Facts checked 2026-10-09 (Claude) — BYBIT, SUPERSEDED same day by [[bybit-dropped-no-eu-leverage]] (venue is now Hyperliquid):**
- Bybit USDC linear perps exist for only **6 of the 10 F8 coins**: BTC, ETH, SOL, DOGE, LINK, XRP (`*PERP`
  symbols). AVAX, NEAR, ADA and SHIB are USDT-only. This matters if `config.py`'s USDC-only/MiCA rule applies
  to the owner's derivatives account.
- Minimum order quantity: BTCPERP 0.001 (~$83 notional at $82.6k), ETHPERP 0.01 (~$25), SOLPERP 0.1 (~$11),
  others ~$5. One rung per coin across the 6 coins is ~$133 notional, which is more than 100 EUR at 1x.
- Open conflict: Disconnect-Cancel-All also cancels resting take-profit orders. Attach the TP to the
  entry order and verify DCP behaviour on Bybit demo before enabling it.
- **F11 is undefined in memory/repo.** Its spec came from a later Fable message that has not been
  provided yet ("slow hedged short basket").

**BOT CORE BUILT 2026-10-09 (Hyperliquid, code + fake-venue tests only, NOT yet run on testnet).**
Owner decisions this session: bot core before F11 (F11 spec still missing); frozen F8 rule verbatim
(1 post-only bid/coin at prior 1m close -2.5%, reduce-only TP +1.2%, 60m market-out) on BTC/ETH/SOL.
**COIN SET WIDENED 2026-10-09 (owner): BTC ETH SOL DOGE XRP ADA** (`ladder.COINS`). The bot skips coins
the venue doesn't list (`Hyperliquid.listed`; testnet lacks XRP), and so does the dashboard (with a note).
All six can fill in the same minute (6 x $12 = $72), so on ~100 EUR each coin needs >=2x isolated, set on
the venue. That is the owner's call at go-live; the bot refuses to run unless every coin is isolated.
Code: `src/coinmon/live/{hyperliquid,control,stop,ladder}.py`, tables `bot_control` + `bot_trades`,
CLI `coinmon bot run|status|resume`, `coinmon stop --now | --drain [--deadline 90m]`, `tests/test_bot.py`.
Env: `COINMON_HL_ADDRESS`, `COINMON_HL_AGENT_KEY`, `COINMON_HL_TESTNET` (default true), `COINMON_BOT_RUNG_USD` (12).
- **Deviation from the frozen rule (venue-forced):** re-peg only when the rung moved >=0.1% (DEADBAND).
  Hyperliquid budgets actions per address: 10k, then 1 per USDC traded, then 1 per 10s. Re-pegging 3 bids
  every minute would burn the 10k in ~2 days. The ledger keeps anchor_close + fill_px per trade.
- Leverage is NOT set by the bot: it reads/logs the venue setting and refuses to run unless every coin
  is isolated (owner's leverage call stands, [[cursed-100-eur-live-ladder]]).
- TP is a plain reduce-only GTC limit placed the cycle after the fill (~3s window), not attached.
- **Testnet needs a mainnet deposit first** (faucet: 1,000 mock USDC only for addresses that deposited on mainnet).
**Owed before real money:** (1) testnet run: ALO place/modify (does modify keep the oid?), TP, IOC close,
fill parsing on a non-empty account, exit classification, PANIC; (2) prove the agent key CANNOT withdraw;
(3) no dead-man switch: Hyperliquid `scheduleCancel` (ccxt `cancel_all_orders_after`) probably needs **$1M
traded volume**. The only evidence is a venue error quoted in ccxt's source ("Required: $1000000"); the docs
don't mention it, so confirm on testnet. It would also cancel the TP. So a dead bot (box asleep) leaves
resting bids that can fill unmanaged; the exposure is <=3 rungs in isolated margin, and accepting it is
the owner's call; (4) heartbeat is recorded and shown on the dashboard, but nothing pushes an alert;
(5) rung size + per-coin leverage = owner's call at go-live; (6) DONE 2026-10-09: timescaledb
`restart: unless-stopped` (compose, plus `docker update` on the running container);
(7) Hyperliquid **$10 minimum order value**; the docs list no reduce-only exemption. A partial fill of a $12 rung
can leave a position whose TP (maybe also the IOC close) is rejected; test on testnet.

**DASHBOARD BUILT 2026-10-09 as a real web app** (a Streamlit version came first; the owner rejected it as
"looks bad" and wanted a professional trader terminal, see [[ui-trader-terminal-look]]). Backend:
`src/coinmon/dashboard/` (FastAPI `api.py`; pure `views.py`; `market.py`). Frontend: `web/` (Vite + React +
TS + Tailwind v4 + TradingView lightweight-charts v5). Run it with `coinmon dashboard` on :8502 (localhost by
default) or the compose service `dashboard`, image `Dockerfile.dashboard`, published on 127.0.0.1:8502.
Layout: top bar (mode, bot heartbeat, websocket status, UTC clock), ticker strip, chart, sidebar (account,
ladder, kill switch), and below the chart the fills ledger and a live liquidation tape.
- **Chart:** candles have hollow up-bodies. Underneath is a Bybit liquidation pane with coverage gaps shaded
  grey. The bot's BID/TP/LONG/LIQ show as price lines, plus a "RULE −2.5%" line when nothing is resting.
  Fills are markers at their exact price.
- **PANIC** is hold-to-fire for 1s. **DRAIN** offers 30m/60m/90m/2h, and when it ends the browser shows a
  notification (Notification API). Resume stays CLI-only.
- **Deliberate deviation from "UI reads only the DB":** the backend also reads PUBLIC Hyperliquid data by
  address with no key (market contexts, candles, the account's positions, orders and equity). It caches it
  server-side because the bot shares the 1200/min IP REST budget (dashboard ~200/min). Live prices come over
  the venue's public WS from the browser, and the tape comes live from Bybit's WS.
- **Writes = the stops only.** POSTs need a JSON body, which acts as the CSRF guard; a test pins this. There
  is no login.
- Colors: up `#12b076` / down `#ea3943`, validated on `#0b0e11`. Their CVD separation is in the 6–8 band,
  so direction always also has arrows, hollow candles, or position.
- Not built yet: account-value history (a burn chart over time needs the bot to snapshot equity into the
  DB) and scoreboard + graveyard.
- **Intent layer (owner, 2026-10-09: "I just want to see the bot doing trades and its intentions"):** on 1m,
  a dashed blue "bid trail" (prior 1m close −2.5%) that hides while a position is open, plus a plain-English
  INTENT sentence (waiting / holding / not running). The owner does not want to learn the screens. Keep the
  plain-English layer when adding features.

- **WAR ROOM mode (owner, 2026-10-09: "take the cool factor to a fuckin extreme… go wild"):** opened by
  the ⚡ button in the top bar, or bookmarked as `/#warroom`. Code is in `web/src/wild/`. Every element
  shows real data:
  - The cascade radar puts each coin's blip at a distance = the share of the drop to its strike left
    this minute. The anchor is one candle read on mount, then rolled from live mids at each minute.
    Liquidations ripple out of their coin's blip.
  - A Geiger tick speeds up as a coin nears its strike. The ECG shows the bot heartbeat and flatlines
    when the bot is down. A pressure gauge shows forced selling over the last 60s.
  - PANIC is a launch button: lift the hazard cover, then hold 1s. Fills and exits trigger full-screen
    FX; whales (>= $100k) shake the screen. Sound is synthesized with Web Audio, with a mute toggle.
  - TEST FX previews the effects and is labeled "PREVIEW · not a real trade". It is not a trade button.
  - Verified with CDP screenshots via headless Chrome. A Chrome launched from bash works; one spawned
    from Node never opened its debug port.

**Coin set facts (checked 2026-10-09, Binance 1m perp, 2024-10 → 2026-09):**
- Days with a 2.5%-in-1m touch: BTC **3**, ETH 23, SOL 22, DOGE 46, XRP 34, ADA 33, NEAR 31, 1000SHIB 27,
  AVAX 25, LINK 22.
- Distinct days by book: BTC/ETH/SOL 32 (~every 3 weeks); +DOGE/XRP/ADA 70; all 10 = 82 (~every 9 days).
- All 10 coins touched in the SAME minute at least once, so simultaneous fills = coins × rung.
- Re-pegs/day under the 0.1% deadband (Sept 2026): BTC 157, ETH 232, SOL 330, DOGE 396, XRP 395, ADA 506,
  NEAR 785, SHIB 422, AVAX 453, LINK 445. 3 coins ≈ 720/day; 10 coins ≈ 4,100/day. Hyperliquid gives a
  10k action buffer, then 1 action per USDC traded, else 1 per 10s.
- Hyperliquid: all 10 are on mainnet (SHIB = `kSHIB`). Day volume is thin on some: DOGE $5.7M, ADA $5.3M,
  AVAX $4.4M, LINK $6.4M, kSHIB $0.3M. **Testnet lacks XRP and LINK.**
- The F8 PASS was pooled over all 10; BTC/ETH/SOL was the owner's first, narrower pick. It was widened
  to 6 the same day.
