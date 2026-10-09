import type { BotState, Config } from "../api";
import { fmtAgo, fmtClock, fmtDur } from "../format";
import type { SocketStatus } from "../hooks";
import { Chip, Dot } from "./Panel";

function Logo() {
  return (
    <svg viewBox="0 0 20 20" className="size-5" aria-hidden>
      <rect width="20" height="20" rx="4" className="fill-up/15" />
      <path d="M4 13 L8 9 L11 11 L16 5" className="stroke-up" strokeWidth="2" fill="none" strokeLinecap="round" />
      <path d="M4 16 H16" className="stroke-ink-3" strokeWidth="1.2" strokeDasharray="1.5 1.5" />
    </svg>
  );
}

function ModePill({ state, now }: { state?: BotState; now: number }) {
  if (!state) return <Chip className="bg-panel-2 text-ink-3">…</Chip>;
  if (!state.db)
    return (
      <Chip className="bg-down/15 text-down" >
        <Dot /> DB DOWN
      </Chip>
    );
  const { mode, reason, deadline_ms } = state;
  const look =
    mode === "RUN"
      ? "bg-up/15 text-up"
      : mode === "DRAIN"
        ? "bg-warn/15 text-warn"
        : "bg-panel-2 text-ink-2";
  const label = mode === "RUN" ? "RUNNING" : mode === "DRAIN" ? "DRAINING" : "HALTED";
  return (
    <span className="flex items-center gap-2" title={`mode ${mode}: ${reason}`}>
      <Chip className={look}>
        <Dot live={mode !== "HALT"} /> {label}
        {mode === "DRAIN" && deadline_ms != null && <span className="num ml-1">{fmtDur(deadline_ms - now)}</span>}
      </Chip>
      <span className="hidden text-xs text-ink-3 xl:inline">{reason}</span>
    </span>
  );
}

function Heartbeat({ state, now }: { state?: BotState; now: number }) {
  if (!state?.db) return null;
  const { heartbeat, heartbeat_ms } = state;
  const [look, text] =
    heartbeat === "alive"
      ? ["text-up", "BOT LIVE"]
      : heartbeat === "stale"
        ? ["text-down", "BOT DOWN"]
        : ["text-ink-3", "BOT NEVER RAN"];
  return (
    <span className={`flex items-center gap-1.5 text-[11px] font-semibold tracking-wider ${look}`} title="last bot cycle">
      <Dot live={heartbeat === "alive"} />
      {text}
      {heartbeat_ms != null && <span className="num font-normal text-ink-3">{fmtAgo(heartbeat_ms, now)}</span>}
    </span>
  );
}

function Feed({ label, status }: { label: string; status: SocketStatus }) {
  const look = status === "open" ? "text-up" : status === "down" ? "text-down" : "text-ink-3";
  return (
    <span className="flex items-center gap-1.5 text-[10px] font-semibold tracking-wider text-ink-3" title={`${label} websocket: ${status}`}>
      <Dot className={look} />
      {label}
    </span>
  );
}

export function TopBar({
  config,
  state,
  now,
  feeds,
  onWarRoom,
}: {
  config: Config;
  state?: BotState;
  now: number;
  feeds: { label: string; status: SocketStatus }[];
  onWarRoom: () => void;
}) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-4 border-b border-line bg-panel px-4">
      <div className="flex items-center gap-2.5">
        <Logo />
        <span className="text-[13px] font-bold tracking-[0.2em]">COINMON</span>
      </div>
      <span className="h-5 w-px bg-line" />
      <span className="text-[13px] text-ink-2">F8 Cascade Ladder</span>
      <Chip className={config.testnet ? "bg-warn/15 text-warn" : "bg-down/15 text-down"}>
        {config.testnet ? "TESTNET" : "MAINNET · REAL MONEY"}
      </Chip>
      <button onClick={onWarRoom} className="wr-enter ml-2" title="the same bot, turned up to eleven">
        ⚡ WAR ROOM
      </button>
      <div className="flex-1" />
      <ModePill state={state} now={now} />
      <Heartbeat state={state} now={now} />
      <span className="h-5 w-px bg-line" />
      <div className="flex items-center gap-3">
        {feeds.map((f) => (
          <Feed key={f.label} {...f} />
        ))}
      </div>
      <span className="h-5 w-px bg-line" />
      <span className="num text-[13px] text-ink-2">
        {fmtClock(now)} <span className="text-ink-3">UTC</span>
      </span>
    </header>
  );
}
