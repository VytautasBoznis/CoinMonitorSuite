import { useCallback, useEffect, useRef, useState } from "react";

import type { Account, BotState, Config, Ctx, Print, Trades } from "../api";
import { arrow, fmtClock, fmtCompactUsd, fmtDur, fmtPct, fmtPx, fmtUsd, tone } from "../format";
import { useNow, type SocketStatus } from "../hooks";
import { Ecg, FxOverlay, LaunchPanic, Odometer, PressureGauge, type Fx } from "./Instruments";
import { coinViews, pressure, pressureSeries, printKey, useAnchors, useNewPrints, useTradeEvents, WHALE_USD, type CoinView } from "./model";
import { heat, Radar, type Ripple } from "./Radar";
import { sfx } from "./sound";

const DRAIN_OPTIONS = [30, 60, 90, 120];
const SEGMENTS = 22;
const SHAKE: Keyframe[] = [
  { transform: "translate(0,0)" },
  { transform: "translate(-7px,3px)" },
  { transform: "translate(7px,-3px)" },
  { transform: "translate(-5px,2px)" },
  { transform: "translate(4px,-1px)" },
  { transform: "translate(0,0)" },
];

/** The War Room: the same bot, data and stop buttons as the terminal, turned up to eleven. */
export function WarRoom({
  config,
  state,
  account,
  trades,
  ctx,
  mids,
  prints,
  feeds,
  onPanic,
  onDrain,
  onExit,
}: {
  config: Config;
  state?: BotState;
  account?: Account;
  trades?: Trades;
  ctx?: Record<string, Ctx>;
  mids: Record<string, number>;
  prints: Print[];
  feeds: { label: string; status: SocketStatus }[];
  onPanic: () => Promise<void>;
  onDrain: (minutes: number) => Promise<void>;
  onExit: () => void;
}) {
  const now = useNow(250);
  const anchors = useAnchors(config.coins, mids);
  const coins = coinViews(config.coins, mids, anchors, account, trades?.rows, state, config.rule, now);
  const ripples = useRef<Ripple[]>([]);
  const stage = useRef<HTMLDivElement>(null);
  const [fx, setFx] = useState<Fx | null>(null);
  const [muted, setMuted] = useState(sfx.muted);
  const fxSeq = useRef(0);

  const show = useCallback((f: Omit<Fx, "id">, ms = 3300) => {
    const id = ++fxSeq.current;
    setFx({ ...f, id });
    window.setTimeout(() => setFx((cur) => (cur?.id === id ? null : cur)), ms);
  }, []);
  const quake = useCallback(() => {
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      stage.current?.animate(SHAKE, { duration: 520, easing: "cubic-bezier(.36,.07,.19,.97)" });
  }, []);

  useNewPrints(prints, (fresh) => {
    for (const p of fresh) {
      const usd = p.price * p.size;
      ripples.current.push({ coin: p.coin, usd, longs: p.side === "Buy", born: performance.now() });
      if (usd >= WHALE_USD) {
        sfx.boom();
        quake();
        show({ kind: "whale", title: `☠ WHALE ${p.side === "Buy" ? "LONG" : "SHORT"} REKT · ${fmtCompactUsd(usd)} ${p.coin}`, detail: "" }, 2400);
      } else sfx.ping(usd);
    }
  });

  useTradeEvents(trades?.rows, ({ kind, trade: t }) => {
    if (kind === "fill") {
      sfx.fill();
      quake();
      show({ kind: "fill", title: "TARGET ACQUIRED", detail: `BOUGHT ${t.sz} ${t.coin} @ ${fmtPx(t.fill_px)}` });
      return;
    }
    const win = (t.net ?? 0) > 0;
    sfx.close(win);
    show({
      kind: win ? "win" : "loss",
      title: win ? "PROFIT SECURED" : t.exit_reason === "time" ? "TIME'S UP" : "POSITION CLOSED",
      detail: `${t.coin} ${fmtPct(t.net)} · ${fmtUsd(t.net_usd, 2, true)}`,
    });
  });

  // Geiger counter: ticks faster as the hottest hunting coin nears its strike.
  const hottest = useRef(0);
  hottest.current = coins.reduce((m, c) => (c.state === "trade" ? m : Math.max(m, c.p)), 0);
  useEffect(() => {
    let t: number;
    const loop = () => {
      const p = hottest.current;
      if (p >= 0.35) sfx.tick(p);
      t = window.setTimeout(loop, p >= 0.35 ? 1300 - 1150 * p : 400);
    };
    loop();
    return () => window.clearTimeout(t);
  }, []);

  const previews: (() => void)[] = [
    () => {
      sfx.fill();
      quake();
      show({ kind: "fill", title: "TARGET ACQUIRED", detail: "PREVIEW · not a real trade" });
    },
    () => {
      sfx.close(true);
      show({ kind: "win", title: "PROFIT SECURED", detail: "PREVIEW · +1.20%" });
    },
    () => {
      sfx.boom();
      quake();
      ripples.current.push({ coin: config.coins[0], usd: 1_200_000, longs: true, born: performance.now() });
      show({ kind: "whale", title: `☠ WHALE LONG REKT · $1.2M ${config.coins[0]} (PREVIEW)`, detail: "" }, 2400);
    },
  ];
  const previewIdx = useRef(0);

  const live = state?.db ? state : undefined;
  const pulse = !state ? "never" : !state.db ? "down" : state.heartbeat;
  const press = pressure(prints, now);
  const closest = coins.filter((c) => c.state !== "trade").sort((a, b) => b.p - a.p)[0];

  return (
    <div className="wr" onPointerDown={() => sfx.wake()}>
      <div className="wr-sky" />
      <div className="wr-sun" />
      <div className="wr-horizon" />
      <div className="wr-floor" />

      <div ref={stage} className="absolute inset-0 flex flex-col">
        <header className="relative z-10 flex h-16 shrink-0 items-center gap-5 px-5">
          <div className="flex items-baseline gap-3">
            <span className="wr-display wr-glitch wr-glow-cyan text-[26px] font-black tracking-[0.18em]" data-text="COINMON">
              COINMON
            </span>
            <span className="wr-display wr-glow-magenta text-[11px] font-bold tracking-[0.45em]">// WAR ROOM</span>
          </div>
          <span
            className={`wr-display border px-2 py-0.5 text-[9px] font-bold tracking-[0.3em] ${
              config.testnet ? "wr-glow-amber border-[rgb(255_176_0/0.5)]" : "wr-glow-red border-[rgb(255_51_85/0.6)]"
            }`}
          >
            {config.testnet ? "TESTNET" : "LIVE MONEY"}
          </span>
          <div className="flex-1" />
          <ModeBadge state={state} now={now} />
          <div className="flex items-center gap-2">
            <Ecg pulse={pulse} />
            <div className="w-[86px]">
              <div className="wr-display text-[8px] tracking-[0.3em] text-[var(--wr-dim)]">BOT PULSE</div>
              <div
                className={`wr-display text-[11px] font-bold tracking-[0.15em] ${
                  pulse === "alive" ? "wr-glow-green" : pulse === "never" ? "wr-dim" : "wr-glow-red"
                }`}
              >
                {pulse === "alive" ? "ALIVE" : pulse === "stale" ? "FLATLINE" : pulse === "down" ? "NO SIGNAL" : "NO PULSE"}
              </div>
            </div>
          </div>
          <div className="wr-display wr-glow-cyan text-[22px] font-bold tabular-nums">
            {fmtClock(now)}
            <span className="ml-1 text-[9px] tracking-[0.3em]">UTC</span>
          </div>
          <div className="flex flex-col gap-0.5">
            {feeds.map((f) => (
              <span key={f.label} className={`wr-display text-[8px] tracking-[0.25em] ${f.status === "open" ? "wr-glow-green" : "wr-glow-red"}`}>
                ● {f.label}
              </span>
            ))}
          </div>
          <button
            className="wr-btn"
            onClick={() => {
              sfx.setMuted(!muted);
              setMuted(!muted);
            }}
          >
            {muted ? "🔇 SFX OFF" : "🔊 SFX ON"}
          </button>
          <button className="wr-btn" title="see the effects without a real trade" onClick={() => previews[previewIdx.current++ % previews.length]()}>
            ◎ TEST FX
          </button>
          <button className="wr-btn" onClick={onExit}>
            ◀ TERMINAL
          </button>
        </header>

        <main className="relative z-10 grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_330px] gap-4 px-4 pb-3">
          <div className="flex min-h-0 flex-col gap-4">
            <section className="wr-panel min-h-0 flex-1">
              <div className="wr-title">TRIGGER PROXIMITY</div>
              <div className="mt-1 min-h-0 flex-1 overflow-y-auto">
                {coins.map((c) => (
                  <ProximityRow key={c.coin} c={c} />
                ))}
                {config.unlisted.length > 0 && (
                  <div className="px-4 py-2 text-[10px] text-[var(--wr-dim)]">{config.unlisted.join(", ")} not on {config.venue}</div>
                )}
              </div>
            </section>
            <section className="wr-panel">
              <div className="wr-title">WAR CHEST</div>
              <WarChest account={account} trades={trades} />
            </section>
          </div>

          <section className="wr-panel glass min-h-0">
            <div className="wr-title">
              CASCADE RADAR
              <span className="ml-auto text-[9px] tracking-[0.2em] text-[var(--wr-dim)]">
                {closest && closest.p > 0 ? (
                  <>
                    CLOSEST <span className={closest.p > 0.5 ? "wr-glow-red" : "wr-glow-amber"}>{closest.coin} {Math.round(closest.p * 100)}%</span>
                  </>
                ) : (
                  "ALL CALM"
                )}
              </span>
            </div>
            <div className="relative min-h-0 flex-1">
              <Radar coins={coins} ripples={ripples} />
            </div>
            <div className="flex flex-wrap justify-center gap-x-5 gap-y-1 px-4 pb-3 text-[10px] text-[var(--wr-dim)]">
              <span>
                <span className="wr-glow-red">STRIKE</span> = the bot buys
              </span>
              <span>blip distance = drop left this minute</span>
              <span>
                <span className="wr-glow-red">◯</span> longs wiped
              </span>
              <span>
                <span className="wr-glow-cyan">◯</span> shorts squeezed
              </span>
              <span>
                <span className="wr-glow-green">◎ LOCKED</span> = in a trade
              </span>
            </div>
          </section>

          <div className="flex min-h-0 flex-col gap-4">
            <section className="wr-panel">
              <div className="wr-title">CASCADE PRESSURE</div>
              <PressureGauge sell={press.sell} buy={press.buy} series={pressureSeries(prints, now)} />
            </section>
            <section className="wr-panel min-h-0 flex-1">
              <div className="wr-title">REKT FEED</div>
              <div className="mt-1 min-h-0 flex-1 overflow-y-auto px-2 pb-2">
                {prints.slice(0, 80).map((p) => {
                  const usd = p.price * p.size;
                  const longs = p.side === "Buy";
                  const whale = usd >= WHALE_USD;
                  return (
                    <div
                      key={printKey(p)}
                      className={`slide-in grid grid-cols-[56px_42px_1fr_auto] items-center gap-2 whitespace-nowrap px-2 py-[3px] text-[11px] ${
                        whale ? "bg-[rgb(255_51_85/0.16)] font-bold" : ""
                      }`}
                    >
                      <span className="text-[var(--wr-dim)]">{fmtClock(p.ts)}</span>
                      <span className="wr-display text-[10px] font-bold">{p.coin}</span>
                      <span className={longs ? "wr-glow-red" : "wr-glow-cyan"}>
                        {whale ? "☠ " : longs ? "▼ " : "▲ "}
                        {longs ? "LONGS WIPED" : "SHORTS SQUEEZED"}
                      </span>
                      <span className="text-right">{fmtCompactUsd(usd)}</span>
                    </div>
                  );
                })}
              </div>
            </section>
            <section className="wr-panel hot">
              <div className="wr-title" style={{ color: "var(--wr-red)", textShadow: "0 0 8px rgb(255 51 85 / .7)" }}>
                KILL SWITCH
              </div>
              <div className="px-4 pb-4 pt-3">
                <LaunchPanic keyed={config.keyed} onPanic={onPanic} />
                <DrainControl canDrain={live?.mode === "RUN"} draining={live?.mode === "DRAIN" ? live.deadline_ms : null} now={now} onDrain={onDrain} />
              </div>
            </section>
          </div>
        </main>

        <Marquee coins={config.coins} mids={mids} ctx={ctx} rule={config.rule} />
      </div>

      <FxOverlay fx={fx} />
      <div className="wr-vignette" />
      <div className="wr-scan" />
    </div>
  );
}

function ModeBadge({ state, now }: { state?: BotState; now: number }) {
  if (!state) return null;
  const [icon, text, glow] = !state.db
    ? ["⚠", "BLIND · DB DOWN", "wr-glow-red"]
    : state.mode === "RUN"
      ? ["◉", "ARMED", "wr-glow-green"]
      : state.mode === "DRAIN"
        ? ["◐", `DRAINING ${state.deadline_ms ? fmtDur(state.deadline_ms - now) : ""}`, "wr-glow-amber"]
        : ["◯", "SAFE · HALTED", "wr-dim"];
  return (
    <div className={`wr-display text-[15px] font-black tracking-[0.25em] ${glow}`} title={state.db ? state.reason : ""}>
      {icon} {text}
    </div>
  );
}

function ProximityRow({ c }: { c: CoinView }) {
  const lit = Math.round(c.p * SEGMENTS);
  const [chip, glow] = c.state === "trade" ? ["IN TRADE", "wr-glow-green"] : c.state === "hunting" ? ["HUNTING", "wr-glow-cyan"] : ["STANDBY", "wr-dim"];
  return (
    <div className="border-b border-[rgb(0_229_255/0.08)] px-4 py-2.5">
      <div className="flex items-baseline gap-3">
        <span className="wr-display w-12 text-[14px] font-black tracking-wider">{c.coin}</span>
        <span className="num flex-1 text-[13px]">{fmtPx(c.mid)}</span>
        <span className={`wr-display text-[8px] font-bold tracking-[0.25em] ${glow}`}>{chip}</span>
      </div>
      {c.state === "trade" && c.pos ? (
        <>
          <div className="mt-1.5 h-2 overflow-hidden bg-[rgb(127_138_168/0.12)]">
            <div
              className="h-full"
              style={{
                width: `${Math.max(0, c.pos.progress) * 100}%`,
                background: "var(--wr-green)",
                boxShadow: "0 0 10px var(--wr-green)",
              }}
            />
          </div>
          <div className="num mt-1 flex justify-between text-[10px] text-[var(--wr-dim)]">
            <span>
              IN {fmtPx(c.pos.entry)} → TP <span className="wr-glow-green">{fmtPx(c.pos.tp)}</span>
            </span>
            <span className={tone(c.pos.upnl)}>{fmtUsd(c.pos.upnl, 2, true)}</span>
            {c.pos.outInMs != null && <span>OUT {fmtDur(c.pos.outInMs)}</span>}
          </div>
        </>
      ) : (
        <>
          <div className="mt-1.5 flex gap-[3px] px-1">
            {Array.from({ length: SEGMENTS }, (_, i) => {
              const col = heat(i / (SEGMENTS - 1));
              return <div key={i} className={`wr-seg ${i < lit ? "on" : ""}`} style={{ ["--seg" as string]: `rgb(${col.join(",")})` }} />;
            })}
          </div>
          <div className="num mt-1 flex justify-between text-[10px] text-[var(--wr-dim)]">
            <span className={tone(c.drop)}>
              {arrow(c.drop)} {fmtPct(c.drop)} /min
            </span>
            <span>
              {c.live ? "BID" : "STRIKE"} {fmtPx(c.strike)}
            </span>
            <span className={c.p > 0.5 ? "wr-glow-red" : ""}>{Math.round(c.p * 100)}%</span>
          </div>
        </>
      )}
    </div>
  );
}

function WarChest({ account, trades }: { account?: Account; trades?: Trades }) {
  const s = trades?.summary;
  if (!account?.configured)
    return (
      <div className="px-4 pb-4 pt-3">
        <div className="wr-display wr-glitch wr-glow-magenta text-[15px] font-black tracking-[0.2em]" data-text="NO WALLET LINKED">
          NO WALLET LINKED
        </div>
        <div className="mt-1.5 text-[10px] leading-relaxed text-[var(--wr-dim)]">
          set COINMON_HL_ADDRESS to watch equity · realized so far{" "}
          <span className={tone(s?.realized_usd)}>{fmtUsd(s?.realized_usd ?? 0, 2, true)}</span>
        </div>
      </div>
    );
  const upnl = account.positions.reduce((m, p) => m + p.upnl, 0);
  return (
    <div className="px-4 pb-4 pt-2">
      <div className="wr-display wr-glow-green text-[30px] font-black leading-none">
        <Odometer value={account.equity} />
      </div>
      <div className="num mt-3 grid grid-cols-3 gap-2 text-[10px]">
        <div>
          <div className="wr-display text-[8px] tracking-[0.25em] text-[var(--wr-dim)]">UPNL</div>
          <div className={tone(upnl)}>{fmtUsd(upnl, 2, true)}</div>
        </div>
        <div>
          <div className="wr-display text-[8px] tracking-[0.25em] text-[var(--wr-dim)]">REALIZED</div>
          <div className={tone(s?.realized_usd)}>{fmtUsd(s?.realized_usd, 2, true)}</div>
        </div>
        <div>
          <div className="wr-display text-[8px] tracking-[0.25em] text-[var(--wr-dim)]">WINS</div>
          <div>{s ? `${s.wins}/${s.closed}` : "—"}</div>
        </div>
      </div>
    </div>
  );
}

function DrainControl({
  canDrain,
  draining,
  now,
  onDrain,
}: {
  canDrain: boolean;
  draining: number | null | undefined;
  now: number;
  onDrain: (m: number) => Promise<void>;
}) {
  const [i, setI] = useState(2);
  const minutes = DRAIN_OPTIONS[i];
  return (
    <div className="mt-3">
      {draining ? (
        <div className="wr-display wr-glow-amber text-center text-[12px] font-bold tracking-[0.2em]">
          DRAINING · FLAT IN {fmtDur(draining - now)}
        </div>
      ) : (
        <div className="flex gap-2">
          <button className="wr-btn amber" onClick={() => setI((i + 1) % DRAIN_OPTIONS.length)} title="change the deadline">
            {minutes >= 120 ? `${minutes / 60}H` : `${minutes}M`}
          </button>
          <button className="wr-btn amber flex-1" disabled={!canDrain} onClick={() => onDrain(minutes)}>
            ⏸ DRAIN
          </button>
        </div>
      )}
      <div className="mt-2 text-center text-[9px] tracking-[0.15em] text-[var(--wr-dim)]">RESUME = CLI · coinmon bot resume</div>
    </div>
  );
}

function Marquee({
  coins,
  mids,
  ctx,
  rule,
}: {
  coins: string[];
  mids: Record<string, number>;
  ctx?: Record<string, Ctx>;
  rule: Config["rule"];
}) {
  const items = (
    <div className="flex items-center">
      {coins.map((c) => {
        const px = mids[c] ?? ctx?.[c]?.mid;
        const ch = px && ctx?.[c] ? px / ctx[c].prev_day - 1 : undefined;
        return (
          <span key={c} className="flex items-center gap-2 px-6 text-[12px]">
            <span className="wr-display font-bold text-[var(--wr-cyan)]">{c}</span>
            <span className="num">{fmtPx(px)}</span>
            <span className={`num ${ch == null ? "" : ch >= 0 ? "wr-glow-green" : "wr-glow-red"}`}>
              {arrow(ch)} {fmtPct(ch)}
            </span>
            <span className="wr-glow-magenta">✦</span>
          </span>
        );
      })}
      <span className="wr-display px-6 text-[10px] tracking-[0.3em] text-[var(--wr-dim)]">
        F8 CASCADE LADDER · BID −{(rule.drop * 100).toFixed(1)}% · TP +{(rule.target * 100).toFixed(1)}% · OUT {rule.hold_ms / 60_000}M
      </span>
      <span className="wr-glow-magenta">✦</span>
    </div>
  );
  return (
    <footer className="relative z-10 h-8 shrink-0 overflow-hidden border-t border-[rgb(255_43_214/0.3)] bg-[rgb(7_3_15/0.85)]">
      <div className="wr-marquee h-full items-center">
        {items}
        {items}
      </div>
    </footer>
  );
}
