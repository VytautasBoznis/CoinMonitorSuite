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
    <nav className="flex h-[58px] shrink-0 items-stretch overflow-x-auto border-b border-line bg-panel">
      {coins.map((coin) => {
        const c = ctx?.[coin];
        const px = mids[coin] ?? c?.mid;
        const change = c && px ? px / c.prev_day - 1 : undefined;
        const active = coin === selected;
        return (
          <button
            key={coin}
            onClick={() => onSelect(coin)}
            className={`group relative flex min-w-[300px] flex-1 items-center justify-between gap-5 border-r border-line px-4 text-left transition-colors ${
              active ? "bg-panel-2" : "hover:bg-panel-2/60"
            }`}
          >
            {active && <span className="absolute inset-x-0 bottom-0 h-[2px] bg-accent" />}
            <div>
              <div className="text-[13px] font-semibold">
                {coin}
                <span className="text-ink-3">-PERP</span>
              </div>
              <div className={`num mt-0.5 text-[11px] ${tone(change)}`}>
                {arrow(change)} {fmtPct(change)}
              </div>
            </div>
            <TickingPrice value={px} className="text-[17px] font-medium" />
            <div className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5 text-[10px]">
              <span className="text-ink-3">FUND 1H</span>
              <span className={`num text-right ${tone(c?.funding)}`}>{fmtPct(c?.funding, 4)}</span>
              <span className="text-ink-3">OI</span>
              <span className="num text-right text-ink-2">{fmtCompactUsd(c?.open_interest_usd)}</span>
              <span className="text-ink-3">VOL 24H</span>
              <span className="num text-right text-ink-2">{fmtCompactUsd(c?.day_volume_usd)}</span>
            </div>
          </button>
        );
      })}
    </nav>
  );
}
