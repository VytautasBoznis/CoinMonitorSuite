import { useEffect, useRef, useState } from "react";

/** Calls ``fn`` now and every ``ms`` after the previous call settles. Keeps the last good data
 *  through errors, so a blip shows as an error badge, not an empty screen. */
export function usePoll<T>(fn: () => Promise<T>, ms: number) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const run = async () => {
      try {
        const d = await fn();
        if (alive) {
          setData(d);
          setError(undefined);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) timer = window.setTimeout(run, ms);
      }
    };
    run();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [fn, ms, tick]);
  return { data, error, refresh: () => setTick((t) => t + 1) };
}

export function useNow(ms = 1000): number {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(t);
  }, [ms]);
  return now;
}

export type SocketStatus = "connecting" | "open" | "down";

type Protocol = {
  sub: (topic: unknown, on: boolean) => unknown;
  ping: unknown;
};

/** A public market-data websocket that re-subscribes after every reconnect. */
export class Socket {
  status: SocketStatus = "connecting";
  onStatus?: (s: SocketStatus) => void;
  private ws?: WebSocket;
  private subs = new Map<string, unknown>();
  private listeners = new Set<(msg: any) => void>();
  private retry?: number;
  private pinger?: number;
  private backoff = 1000;
  private closed = false;

  constructor(
    private url: string,
    private proto: Protocol,
  ) {
    this.open();
  }

  private open() {
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.backoff = 1000;
      this.setStatus("open");
      for (const topic of this.subs.values()) this.send(this.proto.sub(topic, true));
      this.pinger = window.setInterval(() => this.send(this.proto.ping), 20_000);
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      for (const l of this.listeners) l(msg);
    };
    ws.onclose = () => {
      window.clearInterval(this.pinger);
      if (this.closed) return;
      this.setStatus("down");
      this.retry = window.setTimeout(() => this.open(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, 30_000);
    };
    ws.onerror = () => ws.close();
  }

  private setStatus(s: SocketStatus) {
    this.status = s;
    this.onStatus?.(s);
  }

  private send(msg: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  subscribe(key: string, topic: unknown): () => void {
    this.subs.set(key, topic);
    this.send(this.proto.sub(topic, true));
    return () => {
      this.subs.delete(key);
      this.send(this.proto.sub(topic, false));
    };
  }

  listen(fn: (msg: any) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  close() {
    this.closed = true;
    window.clearTimeout(this.retry);
    window.clearInterval(this.pinger);
    this.ws?.close();
  }
}

export const HYPERLIQUID: Protocol = {
  sub: (subscription, on) => ({ method: on ? "subscribe" : "unsubscribe", subscription }),
  ping: { method: "ping" },
};

export const BYBIT_WS = "wss://stream.bybit.com/v5/public/linear";
export const BYBIT: Protocol = {
  sub: (topic, on) => ({ op: on ? "subscribe" : "unsubscribe", args: [topic] }),
  ping: { op: "ping" },
};

export function useSocket(url: string | undefined, proto: Protocol) {
  const [socket, setSocket] = useState<Socket>();
  const [status, setStatus] = useState<SocketStatus>("connecting");
  useEffect(() => {
    if (!url) return;
    const s = new Socket(url, proto);
    s.onStatus = setStatus;
    setSocket(s);
    return () => s.close();
  }, [url, proto]);
  return { socket, status };
}

/** Live mids for ``coins`` from Hyperliquid's allMids channel. */
export function useMids(socket: Socket | undefined, coins: string[]) {
  const [mids, setMids] = useState<Record<string, number>>({});
  const coinsRef = useRef(coins);
  useEffect(() => {
    if (!socket) return;
    const off = socket.listen((m) => {
      if (m.channel !== "allMids") return;
      const next: Record<string, number> = {};
      for (const c of coinsRef.current) if (m.data.mids[c]) next[c] = Number(m.data.mids[c]);
      setMids(next);
    });
    const unsub = socket.subscribe("allMids", { type: "allMids" });
    return () => {
      off();
      unsub();
    };
  }, [socket]);
  return mids;
}
