// Typed client for the dashboard API (src/coinmon/dashboard/api.py). Times are epoch ms UTC.

export type Mode = "RUN" | "DRAIN" | "HALT";

export type Config = {
  venue: string;
  testnet: boolean;
  ws: string;
  coins: string[];
  intervals: string[];
  address: string | null;
  keyed: boolean;
  stale_s: number;
  rule: { drop: number; target: number; hold_ms: number };
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
    }
  | { now: number; db: false; error: string };

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
  candles: (coin: string, interval: string) =>
    req<Candle[]>(`/api/candles?coin=${coin}&interval=${interval}&limit=500`),
  account: () => req<Account>("/api/account"),
  trades: () => req<Trades>("/api/trades?limit=200"),
  liquidations: (coin: string, interval: string, startMs: number, endMs: number) =>
    req<Liquidations>(`/api/liquidations?coin=${coin}&interval=${interval}&start_ms=${startMs}&end_ms=${endMs}`),
  recentPrints: () => req<Print[]>("/api/liquidations/recent?limit=120"),
  panic: () => req<{ flat: boolean }>("/api/panic", post({ confirm: true })),
  drain: (minutes: number) => req<{ mode: Mode; deadline_ms: number }>("/api/drain", post({ minutes })),
};
