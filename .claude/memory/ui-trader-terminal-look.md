---
name: ui-trader-terminal-look
description: "Owner's UI bar (2026-10-09): professional, modern, full 'trader terminal' look. Streamlit was rejected as 'looks bad'; UI work is a real web app (FastAPI + React/Vite/TS + lightweight-charts)."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 31efa2ba-4846-4386-92b6-78bdf2879861
  modified: 2026-10-09T19:37:55.026Z
---

Owner, 2026-10-09, on the first (Streamlit) live-bot dashboard: **"This looks bad bro, i want it to look
professional like modern web design with full on 'trader' feel."** Given the choice, they picked a real web
app over restyling Streamlit.

**Why:** they want to watch the bot and enjoy it ([[live-bot-dashboard-plan]]). A data-notebook look reads
as a toy, and the point of the screen is to make the bot feel real.

**How to apply:**
- Do not build owner-facing UI in Streamlit. The Streamlit viewer stays a research tool only (candles).
- Extend the existing stack in `web/` + `src/coinmon/dashboard/`, matching its look: dark terminal palette
  (bg `#0b0e11`, panels `#12161c`, 1px `#222831` grid), Inter for UI and JetBrains Mono tabular for every
  number, dense panels with uppercase tracking headers, live-ticking prices, green/red always paired with
  ▲/▼ or another second cue.
- Before calling UI work done, screenshot it with headless Chrome
  (`chrome --headless=new --screenshot ... --virtual-time-budget=12000`) and look at it. Use a throwaway demo
  server with fake bot data to check populated states. The Claude-in-Chrome extension was not connected on
  this machine.
- This changes how the UI looks, not when screens get built: the gates in [[ui-roadmap]] still apply.
