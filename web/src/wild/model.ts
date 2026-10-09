// What the War Room shows, derived from the same data as the terminal. Pure functions plus three
// small hooks; nothing here talks to the venue except one candle read per coin on mount.

import { useEffect, useRef, useState } from "react";

import { api, type Account, type BotState, type Config, type Print, type TradeRow } from "../api";

export const WHALE_USD = 100_000;

export type CoinView = {
  coin: string;
  mid?: number;
  anchor?: number; // the prior 1m close: the rule's anchor
  strike?: number; // the bid: the bot's resting one if the account is visible, else the rule's
  live: boolean; // strike is the bot's real resting bid
  drop?: number; // mid vs anchor, this minute
  p: number; // 0 = calm, 1 = price is at the strike (a fill)
  state: "standby" | "hunting" | "trade";
  pos?: { entry: number; tp?: number; szi: number; upnl: number; outInMs?: number; progress: number };
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function coinViews(
  coins: string[],
  mids: Record<string, number>,
  anchors: Record<string, number>,
  account: Account | undefined,
  trades: TradeRow[] | undefined,
  state: BotState | undefined,
  rule: Config["rule"],
  now: number,
): CoinView[] {
  const running = !!state?.db && state.heartbeat === "alive" && state.mode === "RUN";
  const acct = account?.configured ? account : undefined;
  return coins.map((coin) => {
    const mid = mids[coin];
    const anchor = anchors[coin];
    const bid = acct?.orders.find((o) => o.coin === coin && o.side === "B" && !o.reduce_only);
    const strike = bid?.px ?? (anchor ? anchor * (1 - rule.drop) : undefined);
    const drop = mid && anchor ? mid / anchor - 1 : undefined;
    const p = mid && anchor && strike && anchor > strike ? clamp((anchor - mid) / (anchor - strike), 0, 1) : 0;
    const base = { coin, mid, anchor, strike, live: !!bid, drop, p };
    const position = acct?.positions.find((x) => x.coin === coin);
    if (!position) return { ...base, state: running ? "hunting" : "standby" };
    const tp = acct!.orders.find((o) => o.coin === coin && o.reduce_only)?.px;
    const open = trades?.find((t) => t.coin === coin && t.exit_ms == null);
    return {
      ...base,
      state: "trade",
      pos: {
        entry: position.entry_px,
        tp,
        szi: position.szi,
        upnl: position.upnl,
        outInMs: open ? open.fill_ms + rule.hold_ms - now : undefined,
        progress: tp && mid ? clamp((mid - position.entry_px) / (tp - position.entry_px), -1, 1) : 0,
      },
    };
  });
}

/** Forced selling (longs liquidated) and buying in USD over the last ``windowMs``. Prints are newest first. */
export function pressure(prints: Print[], now: number, windowMs = 60_000) {
  let sell = 0;
  let buy = 0;
  for (const p of prints) {
    if (now - p.ts > windowMs) break;
    if (p.side === "Buy") sell += p.price * p.size;
    else buy += p.price * p.size;
  }
  return { sell, buy };
}

/** Forced selling per ``stepMs`` bucket, oldest first, for the gauge's sparkline. */
export function pressureSeries(prints: Print[], now: number, buckets = 30, stepMs = 10_000): number[] {
  const out = new Array<number>(buckets).fill(0);
  for (const p of prints) {
    const i = buckets - 1 - Math.floor((now - p.ts) / stepMs);
    if (i < 0) break;
    if (i < buckets && p.side === "Buy") out[i] += p.price * p.size;
  }
  return out;
}

/** Each coin's prior 1m close: one candle read on mount, then rolled from the live mids at every
 *  minute boundary (the mid at the boundary is the closing price to within a tick). */
export function useAnchors(coins: string[], mids: Record<string, number>) {
  const [anchors, setAnchors] = useState<Record<string, number>>({});
  const latest = useRef(mids);
  latest.current = mids;
  const key = coins.join(",");
  useEffect(() => {
    let alive = true;
    for (const coin of key.split(",")) {
      api.candles(coin, "1m", 10).then(
        (cs) => alive && cs.length > 1 && setAnchors((a) => ({ ...a, [coin]: cs[cs.length - 2].close })),
        () => undefined,
      );
    }
    let timer: number;
    const roll = () => {
      timer = window.setTimeout(() => {
        setAnchors((a) => ({ ...a, ...latest.current }));
        roll();
      }, 60_000 - (Date.now() % 60_000) + 30);
    };
    roll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [key]);
  return anchors;
}

/** Calls ``onNew`` with prints that arrived since mount (older ones are history, not events). */
export function useNewPrints(prints: Print[], onNew: (fresh: Print[]) => void) {
  const seen = useRef(new Set<string>());
  const since = useRef(Date.now() - 5_000);
  const cb = useRef(onNew);
  cb.current = onNew;
  useEffect(() => {
    const fresh: Print[] = [];
    for (const p of prints) {
      const k = printKey(p);
      if (seen.current.has(k)) continue;
      seen.current.add(k);
      if (p.ts >= since.current) fresh.push(p);
    }
    if (fresh.length) cb.current(fresh);
  }, [prints]);
}

export const printKey = (p: Print) => `${p.coin}${p.ts}${p.side}${p.price}${p.size}`;

export type TradeEvent = { kind: "fill" | "exit"; trade: TradeRow };

/** Calls ``onEvent`` when a round trip opens or closes after mount. */
export function useTradeEvents(rows: TradeRow[] | undefined, onEvent: (e: TradeEvent) => void) {
  const seen = useRef<Map<number, boolean>>(null);
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    if (!rows) return;
    if (!seen.current) {
      seen.current = new Map(rows.map((r) => [r.entry_oid, r.exit_ms != null]));
      return;
    }
    for (const r of rows) {
      const closed = r.exit_ms != null;
      const was = seen.current.get(r.entry_oid);
      if (was === undefined) cb.current({ kind: "fill", trade: r });
      if (closed && was !== true) cb.current({ kind: "exit", trade: r });
      seen.current.set(r.entry_oid, closed);
    }
  }, [rows]);
}
