import type { Print } from "../api";
import { fmtClock, fmtCompactUsd, fmtPx } from "../format";
import type { SocketStatus } from "../hooks";
import { Dot, Panel } from "./Panel";

const WHALE_USD = 100_000;

/** Live Bybit liquidation prints for the ladder's coins. "Buy" = a long was liquidated. */
export function LiqTape({ prints, status }: { prints: Print[]; status: SocketStatus }) {
  return (
    <Panel
      title="Liquidation tape"
      right={
        <span className={`flex items-center gap-1.5 text-[10px] font-semibold tracking-wider ${status === "open" ? "text-up" : "text-ink-3"}`}>
          <Dot live={status === "open"} /> {status === "open" ? "LIVE · BYBIT" : status.toUpperCase()}
        </span>
      }
    >
      <div className="h-full overflow-y-auto">
        {prints.map((p) => {
          const usd = p.price * p.size;
          const longs = p.side === "Buy";
          return (
            <div
              key={`${p.coin}${p.ts}${p.side}${p.price}${p.size}`}
              className={`slide-in num grid grid-cols-[62px_38px_1fr_64px_78px] items-center gap-2 border-b border-line/50 px-3 py-[5px] text-[11px] ${
                usd >= WHALE_USD ? (longs ? "bg-down/10 font-semibold" : "bg-up/10 font-semibold") : ""
              }`}
            >
              <span className="text-ink-3">{fmtClock(p.ts)}</span>
              <span className="font-sans font-semibold">{p.coin}</span>
              <span className={longs ? "text-down" : "text-up"}>{longs ? "▼ LONGS REKT" : "▲ SHORTS REKT"}</span>
              <span className="text-right">{fmtCompactUsd(usd)}</span>
              <span className="text-right text-ink-2">{fmtPx(p.price)}</span>
            </div>
          );
        })}
        {!prints.length && <div className="p-3 text-[12px] text-ink-3">Waiting for the next liquidation…</div>}
      </div>
    </Panel>
  );
}
