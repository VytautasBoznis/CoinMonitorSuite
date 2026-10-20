// The scoreboard and the graveyard: every idea that went through a pre-registered probe, with the
// numbers that decided it (from the probe logs in runs/). Add a row whenever a probe reports.

export type Standing = {
  id: string;
  name: string;
  status: "LIVE" | "CERTIFIED" | "PARKED" | "LEAD";
  since: string;
  what: string;
  evidence: string;
  blocker: string;
  backtest?: { perEvent: number; targetHit: number }; // the live book is scored against these
};

export type Grave = { id: string; name: string; died: string; what: string; cause: string; epitaph: string };

/** The deploy bar every row is judged against ([[live-yield-hurdle]]). */
export const HURDLE = "Real money needs ≥5%/yr expected forward, judged on the recent regime, after every cost.";
export const WINNERS_NEEDED = 3;

export const STANDING: Standing[] = [
  {
    id: "F8",
    name: "Cascade ladder",
    status: "LIVE",
    since: "2026-10-13",
    what: "A resting bid 2.5% under the last 1m close on 6 perps; sell at +1.2% or after 60 minutes.",
    evidence: "Backtest +0.51%/event (N 2,261, 2021-26), positive in 6 of 6 years, target hit 86.3%.",
    blocker:
      "The last 24 months clear 5%/yr only if every touch fills, and that is what this live book measures. It needs ~190 fills (~1.5 years at the backtest's pace) before the live mean can tell +0.5% from zero.",
    backtest: { perEvent: 0.0051, targetHit: 0.863 },
  },
  {
    id: "F1",
    name: "Tail-gated funding carry",
    status: "PARKED",
    since: "2026-07-31",
    what: "Delta-neutral funding harvest, switched on only while funding runs ≥30%/yr.",
    evidence: "Passed 5 of 5 rules: +18.9%/yr on the capital it uses.",
    blocker: "As one account it made +2.47%/yr over the last 24 months, under the bar. Kept as an overlay.",
  },
  {
    id: "W3",
    name: "Funding carry",
    status: "CERTIFIED",
    since: "2026-07-06",
    what: "Always-on delta-neutral funding harvest across 41 perps.",
    evidence: "The project's only certificate: +2.23%/yr out of sample, t 4.08, 12× its null.",
    blocker: "The recent half earns ~+0.18%/yr. It waits for funding to come back.",
  },
  {
    id: "B20",
    name: "US-close hour (21-23 UTC)",
    status: "LEAD",
    since: "2026-07-18",
    what: "Long the majors from 21:00 to 23:00 UTC, flat the rest of the day.",
    evidence: "+16%/yr median at maker fees, all 5 majors positive; out-of-asset ETH t 4.7, BNB t 6.0.",
    blocker: "At taker fees it loses 30-52%/yr: 52-90% of entries must fill as maker. Only live fills settle that.",
  },
];

export const GRAVES: Grave[] = [
  {
    id: "F4",
    name: "Token-unlock shorts",
    died: "2026-10-19",
    what: "Short a coin 7 days before insiders' tokens unlock.",
    cause: "+1.08%/event over 575 unlocks, but the 95% CI (−0.63 to +2.73) spans zero and it doesn't beat shorting the same coin in a random week.",
    epitaph: "Indistinguishable from any other week.",
  },
  {
    id: "F11",
    name: "Post-listing drift short",
    died: "2026-10-15",
    what: "Short new listings from day 8 to day 98, hedged with an alt basket.",
    cause: "New listings do drift down (median short +21%), but 1 in 4 doubles first and liquidates a 1x short. Binance +2.0%/event with CI spanning zero, Bybit −4.6%.",
    epitaph: "Right about the coin. Liquidated anyway.",
  },
  {
    id: "F8S",
    name: "Short-squeeze ladder",
    died: "2026-10-14",
    what: "F8 mirrored: a resting ask 2.5% above the last close, take profit at −1.2%.",
    cause: "−0.67%/event (N 1,851), 0 of 6 years positive; a quarter of fills would breach a 20x liquidation.",
    epitaph: "Crashes snap back. Squeezes don't.",
  },
  {
    id: "F3",
    name: "Quarterly basis carry",
    died: "2026-10-08",
    what: "Buy spot and sell the quarterly future while the basis pays >10%/yr; hold to expiry.",
    cause: "+3.94%/yr counting idle time, under the bar. No trade has qualified since March 2025.",
    epitaph: "20 trades, 20 wins, then nothing.",
  },
  {
    id: "F5",
    name: "Polymarket favorites",
    died: "2026-10-08",
    what: "Back the 90-97¢ favorite a day before the market resolves.",
    cause: "Favorites won 92.4% at an average price of 93.9¢: a −1.53pp gap where +1.5pp was needed.",
    epitaph: "The favorites were overpriced.",
  },
  {
    id: "F6",
    name: "New-listing funding",
    died: "2026-10-08",
    what: "Collect a new perp's first-week funding, hedged.",
    cause: "Only 45% (Binance) and 41% (Bybit) of listings pay; Binance's +1.5% mean is a few big ones, and the hedge needs scarce borrow.",
    epitaph: "The average was a few lottery tickets.",
  },
  {
    id: "F7",
    name: "Funding-clock scalp",
    died: "2026-10-08",
    what: "Fade the flow around the 00/08/16 UTC funding settlements.",
    cause: "−12bp/event (t −0.85, N 3,384). Extreme funding on the majors has been nearly extinct since 2025.",
    epitaph: "Died exactly as pre-registered.",
  },
  {
    id: "F9",
    name: "Weekend vol premium",
    died: "2026-10-08",
    what: "Sell BTC and ETH options over the weekend.",
    cause: "The index 'premium' was the weekend calendar effect; real Monday options have priced at or below realized vol since 2023.",
    epitaph: "The premium was a calendar.",
  },
  {
    id: "B17",
    name: "Trend-following portfolio",
    died: "2026-07-18",
    what: "Vol-targeted time-series momentum across the perps, long and short.",
    cause: "Median −11.6%/yr, Sharpe 0.24, 3 of 16 configs positive.",
    epitaph: "The trend was a 2017-2021 thing.",
  },
  {
    id: "B18/19",
    name: "Open-interest signals",
    died: "2026-07-18",
    what: "Fade crowded open interest, or follow a trend only while OI rises.",
    cause: "A real but tiny reversal signal (IC −0.03), too weak to pay fees. As a trend filter it made things worse: 0 of 16 positive.",
    epitaph: "Rising OI means crowded, not confirmed.",
  },
  {
    id: "B13/14",
    name: "Low volatility",
    died: "2026-07-18",
    what: "Long the calm coins, short the wild ones.",
    cause: "The long leg lost to just holding BTC (+12.9% vs +15.6%/yr). The short leg paid only in the 2022 crash, on a survivors-only universe.",
    epitaph: "A 2022 crash bet in disguise.",
  },
  {
    id: "B16",
    name: "Funding crowding",
    died: "2026-07-06",
    what: "Long the lowest-funding perps, short the highest.",
    cause: "Win rate ~50% on every config, median −0.23%/yr.",
    epitaph: "A coin flip with fees.",
  },
  {
    id: "H7",
    name: "Order flow (CVD)",
    died: "2026-07-06",
    what: "Trade the next 4h bar on this bar's taker buy/sell imbalance.",
    cause: "Taker buying moves price inside its own bar (corr +0.36 to +0.40), then nothing: next-bar IC ≈ 0 on 4 of 4 majors.",
    epitaph: "Priced in before the bar closed.",
  },
  {
    id: "B9/10",
    name: "Maker-fee rescue",
    died: "2026-07-06",
    what: "Re-run the GA's best rules at maker fees.",
    cause: "Only 1 of 7 flipped positive. Fees were not the killer; the signal was missing.",
    epitaph: "Cheaper losing is still losing.",
  },
  {
    id: "B1-4",
    name: "Candle-shape signals",
    died: "2026-07-06",
    what: "Post-shock bounce, volume shocks, cross-venue lead-lag, rebalancing premium.",
    cause: "0 of 4 passed. No bounce, Binance and Bybit move together within the bar, rebalancing a near miss (positive in 68% of rolling years, 70% needed).",
    epitaph: "The candles had nothing to say.",
  },
  {
    id: "W5",
    name: "Cross-sectional momentum",
    died: "2026-07-05",
    what: "Weekly: long the top-ranked coins, short the bottom.",
    cause: "The best of 162 configs was refuted: win 48%, expectancy CI straddles zero.",
    epitaph: "The best of 162 was luck.",
  },
  {
    id: "GA",
    name: "Evolved indicator strategies",
    died: "2026-07-03",
    what: "A genetic search over RSI/EMA/breakout-style rules.",
    cause: "0 certified across 3 sweeps, every expectancy negative after fees. The search found artifacts; it is now banned.",
    epitaph: "+2601% on holdout, from a handful of trades.",
  },
];
