---
name: live-bot-dashboard-plan
description: "DIRECTIVE 2026-10-09: owner LIFTED the >=3-winner UI gate for a live-bot inspection dashboard (bot + UI built together). No manual trade button; two manual STOP modes (PANIC now / DRAIN planned). Agreed build order + pre-money safety rules from the Fable conversation."
metadata:
  node_type: memory
  type: project
  originSessionId: f655be08-d28b-48b8-91b6-b4b28bbce97c
  modified: 2026-10-09T17:29:03.156Z
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

**Facts checked 2026-10-09 (Claude):**
- Bybit USDC linear perps exist for only **6 of the 10 F8 coins**: BTC, ETH, SOL, DOGE, LINK, XRP (`*PERP`
  symbols). AVAX, NEAR, ADA and SHIB are USDT-only. This matters if `config.py`'s USDC-only/MiCA rule applies
  to the owner's derivatives account.
- Minimum order quantity: BTCPERP 0.001 (~$83 notional at $82.6k), ETHPERP 0.01 (~$25), SOLPERP 0.1 (~$11),
  others ~$5. One rung per coin across the 6 coins is ~$133 notional, which is more than 100 EUR at 1x.
- Open conflict: Disconnect-Cancel-All also cancels resting take-profit orders. Attach the TP to the
  entry order and verify DCP behaviour on Bybit demo before enabling it.
- **F11 is undefined in memory/repo.** Its spec came from a later Fable message that has not been
  provided yet ("slow hedged short basket").
