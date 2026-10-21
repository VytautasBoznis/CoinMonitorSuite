// Typed client for the dashboard API (src/coinmon/dashboard/api.py). Times are epoch ms UTC.

export type Mode = "RUN" | "DRAIN" | "HALT";

/** A ladder's knobs; ``trend_ms`` gates bids to a coin up over that span (null: no gate). */
export type Rule = { drop: number; target: number; hold_ms: number; trend_ms?: number | null };

export type Config = {
  venue: string;
  testnet: boolean;
  ws: string;
  coins: string[]; // the bot's coins this venue lists
  unlisted: string[]; // the bot's coins it does not (testnet lacks some)
  intervals: string[];
  address: string | null;
  keyed: boolean;
  stale_s: number;
  rule: Rule; // the live bot's
};

export type BotState =
  | {
      now: number;
      db: true;
      mode: Mode;
      reason: string;
      deadline_ms: number | null;
      updated_ms: number;
      heartbeat_ms: number | null;
      heartbeat: "alive" | "stale" | "never";
      started_ms: number | null; // first heartbeat: a paper bot's bar is judged from it
      book: Order[] | null; // a paper bot's resting simulated orders (the live bot's are on the venue)
    }
  | { now: number; db: false; error: string };

/** A bot's own backtest, frozen before its first run (runs/swarm_baselines.log). */
export type Baseline = { per_year: number; mean: number; ci: [number, number]; tp_hit: number; yield_yr: number };

/** The live bot first, then the swarm's paper bots. */
export type Bot = {
  id: string;
  paper: boolean;
  question: string;
  bar: string;
  rule: Rule;
  baseline: Baseline;
  state: BotState;
};

/** The promotion bar's verdict, applied as written (src/coinmon/live/score.py). */
export type Verdict = {
  status: "not started" | "too early" | "extended" | "pass" | "fail";
  at_ms: number | null; // the judging date
  n?: number;
  ci?: [number, number] | null;
  yield_yr?: number | null;
};

/** A bot's forward record next to its backtest. */
export type Card = {
  id: string;
  n: number;
  mean: number | null;
  ci: [number, number] | null; // 95%, bootstrap over UTC days
  yield_yr: number | null;
  since_ms: number | null;
  open: number;
  expected_n: number; // at the backtest's pace
  tp_hit: number | null;
  net_usd: number;
  vs_backtest: "too early" | "below" | "above" | "in line";
  bar?: Verdict;
  capture?: { twin: number; caught: number; live_only: number; gap: number | null; n_gap: number };
};

export type Ctx = {
  mark: number;
  mid: number;
  prev_day: number;
  funding: number; // hourly rate
  open_interest_usd: number;
  day_volume_usd: number;
};

export type Candle = { time: number; open: number; high: number; low: number; close: number; volume: number };

export type Position = {
  coin: string;
  szi: number;
  entry_px: number;
  value: number;
  upnl: number;
  liq_px: number | null;
  leverage: string;
  margin: number;
};

export type Order = { coin: string; oid: number; side: "A" | "B"; px: number; sz: number; reduce_only: boolean; time: number };

export type Account =
  | { configured: false }
  | {
      configured: true;
      equity: number;
      margin_used: number;
      notional: number;
      withdrawable: number;
      positions: Position[];
      orders: Order[];
    };

/** The venue's record of the account: equity and all-time PnL (fees and funding included). */
export type BurnPoint = { time: number; equity: number; pnl: number };
export type Burn = { configured: false } | { configured: true; points: BurnPoint[] };

export type TradeRow = {
  coin: string;
  entry_oid: number;
  fill_ms: number;
  sz: number;
  notional: number;
  leverage: string;
  liq_px: number | null;
  anchor_close: number | null;
  fill_px: number;
  drop: number | null;
  tp_px: number | null;
  exit_px: number | null;
  exit_ms: number | null;
  exit_reason: string | null;
  exit_dir: string | null;
  fees: number;
  net: number | null;
  net_usd: number | null;
};

export type Trades = {
  rows: TradeRow[];
  summary: { open: number; closed: number; wins: number; realized_usd: number; fees_usd: number };
};

export type Liquidations = {
  buckets: { time: number; sell: number; buy: number }[];
  gaps: [number, number][];
  coverage: number;
};

/** One liquidation print. side "Buy" = a long was liquidated = forced selling. */
export type Print = { coin: string; ts: number; side: "Buy" | "Sell"; price: number; size: number };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = body?.detail;
    throw new ApiError(r.status, typeof detail === "string" ? detail : `${r.status} ${r.statusText}`);
  }
  return body as T;
}

const post = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  config: () => req<Config>("/api/config"),
  state: () => req<BotState>("/api/state"),
  market: () => req<Record<string, Ctx>>("/api/market"),
  candles: (coin: string, interval: string, limit = 500) =>
    req<Candle[]>(`/api/candles?coin=${coin}&interval=${interval}&limit=${limit}`),
  account: () => req<Account>("/api/account"),
  burn: () => req<Burn>("/api/burn"),
  bots: () => req<Bot[]>("/api/bots"),
  scoreboard: () => req<Card[]>("/api/scoreboard"),
  trades: (bot?: string) => req<Trades>(`/api/trades?limit=200${bot ? `&bot=${bot}` : ""}`),
  liquidations: (coin: string, interval: string, startMs: number, endMs: number) =>
    req<Liquidations>(`/api/liquidations?coin=${coin}&interval=${interval}&start_ms=${startMs}&end_ms=${endMs}`),
  recentPrints: () => req<Print[]>("/api/liquidations/recent?limit=120"),
  panic: () => req<{ flat: boolean }>("/api/panic", post({ confirm: true })),
  drain: (minutes: number) => req<{ mode: Mode; deadline_ms: number }>("/api/drain", post({ minutes })),
};
