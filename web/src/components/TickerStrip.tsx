import { useEffect, useRef, useState } from "react";

import type { Ctx } from "../api";
import { arrow, fmtCompactUsd, fmtPct, fmtPx, tone } from "../format";

/** A price that flashes green/red for a moment when it ticks up/down. */
export function TickingPrice({ value, className = "" }: { value?: number; className?: string }) {
  const prev = useRef(value);
  const [flash, setFlash] = useState<{ dir: "up" | "down"; n: number }>();
  useEffect(() => {
    if (value != null && prev.current != null && value !== prev.current)
      setFlash((f) => ({ dir: value > prev.current! ? "up" : "down", n: (f?.n ?? 0) + 1 }));
    prev.current = value;
  }, [value]);
  return (
    <span
      key={flash?.n}
      className={`num rounded-[3px] px-1 -mx-1 ${flash ? `flash-${flash.dir}` : ""} ${
        flash?.dir === "up" ? "text-up" : flash?.dir === "down" ? "text-down" : ""
      } ${className}`}
    >
      {fmtPx(value)}
    </span>
  );
}

export function TickerStrip({
  coins,
  selected,
  onSelect,
  mids,
  ctx,
}: {
  coins: string[];
  selected: string;
  onSelect: (coin: string) => void;
  mids: Record<string, number>;
  ctx?: Record<string, Ctx>;
}) {
  return (
    <nav className="flex h-[54px] shrink-0 items-stretch overflow-x-auto border-b border-line bg-panel">
      {coins.map((coin) => {
        const c = ctx?.[coin];
        const px = mids[coin] ?? c?.mid;
        const change = c && px ? px / c.prev_day - 1 : undefined;
        const active = coin === selected;
        return (
          <button
            key={coin}
            onClick={() => onSelect(coin)}
            title={c ? `open interest ${fmtCompactUsd(c.open_interest_usd)} · 24h volume ${fmtCompactUsd(c.day_volume_usd)}` : undefined}
            className={`group relative flex min-w-[200px] flex-1 flex-col justify-center gap-1 border-r border-line px-4 text-left transition-colors ${
              active ? "bg-panel-2" : "hover:bg-panel-2/60"
            }`}
          >
            {active && <span className="absolute inset-x-0 bottom-0 h-[2px] bg-accent" />}
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[12px] font-semibold">
                {coin}
                <span className="text-ink-3">-PERP</span>
              </span>
              <span className={`num text-[11px] ${tone(change)}`}>
                {arrow(change)} {fmtPct(change)}
              </span>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <TickingPrice value={px} className="text-[16px] font-medium" />
              <span className="num text-[10px] text-ink-3">
                FUND <span className={tone(c?.funding)}>{fmtPct(c?.funding, 4)}</span>
              </span>
            </div>
          </button>
        );
      })}
    </nav>
  );
}
