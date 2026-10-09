import { useCallback, useEffect, useRef, useState } from "react";

import { api, type Config, type Print } from "./api";
import { AccountPanel } from "./components/AccountPanel";
import { Controls } from "./components/Controls";
import { FillsTable } from "./components/FillsTable";
import { LadderPanel } from "./components/LadderPanel";
import { LiqTape } from "./components/LiqTape";
import { PriceChart } from "./components/PriceChart";
import { TickerStrip } from "./components/TickerStrip";
import { Toasts, type Toast } from "./components/Toasts";
import { TopBar } from "./components/TopBar";
import { BYBIT, BYBIT_WS, HYPERLIQUID, useMids, useNow, usePoll, useSocket } from "./hooks";
import { sfx } from "./wild/sound";
import { WarRoom } from "./wild/WarRoom";

const TAPE_MAX = 400; // the War Room's pressure gauge reads 5 minutes of it

export default function App() {
  const config = usePoll(api.config, 60_000);
  if (!config.data)
    return (
      <div className="grid h-full place-items-center text-[13px] text-ink-3">
        {config.error ? <span className="text-down">dashboard API unreachable: {config.error}</span> : "connecting…"}
      </div>
    );
  return <Terminal config={config.data} />;
}

function Terminal({ config }: { config: Config }) {
  const now = useNow(1000);
  const state = usePoll(api.state, 2_000);
  const account = usePoll(api.account, 3_000);
  const trades = usePoll(api.trades, 5_000);
  const market = usePoll(api.market, 15_000);
  const [coin, setCoin] = useState(config.coins[0]);
  const [interval, setChartInterval] = useState("1m");
  const hl = useSocket(config.ws, HYPERLIQUID);
  const bybit = useSocket(BYBIT_WS, BYBIT);
  const live = useMids(hl.socket, config.coins);
  const ctxMids = Object.fromEntries(Object.entries(market.data ?? {}).map(([c, x]) => [c, x.mid]));
  const mids = { ...ctxMids, ...live }; // websocket ticks win; REST context until the first tick
  const prints = useTape(bybit.socket, config.coins);
  const { toasts, push, dismiss } = useToasts();
  const [warRoom, setWarRoom] = useState(
    () => location.hash === "#warroom" || localStorage.getItem("coinmon.warroom") === "1",
  );
  const toggleWarRoom = (on: boolean) => {
    if (on) sfx.wake(); // inside the click: browsers start audio only from a gesture
    localStorage.setItem("coinmon.warroom", on ? "1" : "0");
    setWarRoom(on);
  };

  // DRAIN finishing is the one moment worth a browser notification (owner's planned downtime).
  const lastMode = useRef<string>(undefined);
  const mode = state.data?.db ? state.data.mode : undefined;
  const reason = state.data?.db ? state.data.reason : "";
  useEffect(() => {
    if (lastMode.current === "DRAIN" && mode === "HALT") {
      const text = `DRAIN ended: mode HALT (${reason}).`;
      push({ kind: reason === "drained" ? "ok" : "warn", text, sticky: true });
      if ("Notification" in window && Notification.permission === "granted") new Notification("COINMON", { body: text });
    }
    lastMode.current = mode;
  }, [mode, reason, push]);

  const onPanic = async () => {
    try {
      const { flat } = await api.panic();
      push(
        flat
          ? { kind: "ok", text: "PANIC done: the venue reports flat. Mode HALT." }
          : { kind: "error", text: "PANIC did NOT confirm flat after retries. Check the venue NOW.", sticky: true },
      );
    } catch (e) {
      push({ kind: "error", text: `PANIC failed: ${(e as Error).message}`, sticky: true });
    }
    state.refresh();
    account.refresh();
  };
  const onDrain = async (minutes: number) => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
    try {
      await api.drain(minutes);
      push({ kind: "warn", text: `DRAIN started: flat at market within ${minutes} min.` });
    } catch (e) {
      push({ kind: "error", text: `DRAIN failed: ${(e as Error).message}` });
    }
    state.refresh();
  };

  const feeds = [
    { label: "HL", status: hl.status },
    { label: "BYBIT", status: bybit.status },
  ];
  if (warRoom)
    return (
      <>
        <WarRoom
          config={config}
          state={state.data}
          account={account.data}
          trades={trades.data}
          ctx={market.data}
          mids={mids}
          prints={prints}
          feeds={feeds}
          onPanic={onPanic}
          onDrain={onDrain}
          onExit={() => toggleWarRoom(false)}
        />
        <Toasts toasts={toasts} dismiss={dismiss} />
      </>
    );
  return (
    <div className="flex h-full min-w-[1180px] flex-col">
      <TopBar config={config} state={state.data} now={now} feeds={feeds} onWarRoom={() => toggleWarRoom(true)} />
      {(state.error || (state.data && !state.data.db)) && (
        <div className="shrink-0 bg-down/15 px-4 py-1.5 text-[12px] text-down">
          {state.error
            ? `Dashboard API unreachable: ${state.error}`
            : `Control store unreachable, so the bot places no new risk: ${state.data && !state.data.db ? state.data.error : ""}`}
        </div>
      )}
      <TickerStrip coins={config.coins} selected={coin} onSelect={setCoin} mids={mids} ctx={market.data} />
      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_340px] grid-rows-[minmax(0,1fr)_270px] gap-px bg-line">
        <PriceChart
          coin={coin}
          interval={interval}
          intervals={config.intervals}
          onInterval={setChartInterval}
          socket={hl.socket}
          state={state.data}
          account={account.data}
          trades={trades.data?.rows}
          rule={config.rule}
        />
        <aside className="row-span-2 flex min-h-0 flex-col gap-px overflow-y-auto bg-line">
          <AccountPanel account={account.data} error={account.error} address={config.address} summary={trades.data?.summary} />
          <LadderPanel coins={config.coins} unlisted={config.unlisted} venue={config.venue} account={account.data} trades={trades.data?.rows} mids={mids} rule={config.rule} now={now} />
          <Controls state={state.data} keyed={config.keyed} now={now} onPanic={onPanic} onDrain={onDrain} />
        </aside>
        <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_380px] gap-px bg-line">
          <FillsTable trades={trades.data} rule={config.rule} now={now} />
          <LiqTape prints={prints} status={bybit.status} />
        </div>
      </main>
      <Toasts toasts={toasts} dismiss={dismiss} />
    </div>
  );
}

/** Stored prints (last 24h) first, then live prints from Bybit's allLiquidation channel. */
function useTape(socket: ReturnType<typeof useSocket>["socket"], coins: string[]) {
  const [prints, setPrints] = useState<Print[]>([]);
  const topics = coins.join(","); // stable across config refreshes
  useEffect(() => {
    api.recentPrints().then((rows) => setPrints((live) => merge(live, rows)), () => undefined);
  }, []);
  useEffect(() => {
    if (!socket) return;
    const off = socket.listen((m) => {
      if (typeof m.topic !== "string" || !m.topic.startsWith("allLiquidation.")) return;
      const rows: Print[] = m.data.map((d: { T: number; s: string; S: "Buy" | "Sell"; v: string; p: string }) => ({
        coin: d.s.replace(/USDT$/, ""),
        ts: d.T,
        side: d.S,
        price: Number(d.p),
        size: Number(d.v),
      }));
      setPrints((old) => merge(old, rows));
    });
    const unsubs = topics.split(",").map((c) => socket.subscribe(`liq:${c}`, `allLiquidation.${c}USDT`));
    return () => {
      off();
      unsubs.forEach((u) => u());
    };
  }, [socket, topics]);
  return prints;
}

function merge(a: Print[], b: Print[]): Print[] {
  const seen = new Map<string, Print>();
  for (const p of [...a, ...b]) seen.set(`${p.coin}${p.ts}${p.side}${p.price}${p.size}`, p);
  return [...seen.values()].sort((x, y) => y.ts - x.ts).slice(0, TAPE_MAX);
}

function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = ++seq.current;
      setToasts((ts) => [...ts, { ...t, id }]);
      if (!t.sticky) window.setTimeout(() => dismiss(id), 6_000);
    },
    [dismiss],
  );
  return { toasts, push, dismiss };
}
