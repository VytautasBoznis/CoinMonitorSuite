import { useEffect, useId, useRef, useState, type PointerEvent } from "react";

import type { BurnPoint } from "../api";
import { arrow, fmtDateTime, fmtPct, fmtUsd, tone } from "../format";

const H = 44;
const PAD = 4; // keeps the 2px line and the hover dot inside the box

/** Equity beside the burn meter: the account's all-time P&L as the venue records it (fees and
 *  funding included), drawn around $0. Green above the dotted zero line, red below; the caption
 *  says it in words. Hovering a point puts its time and value in the caption. */
export function EquityBurn({ equity, points }: { equity: number; points?: BurnPoint[] }) {
  const [hover, setHover] = useState<BurnPoint>();
  const last = points?.at(-1);
  const putIn = last ? last.equity - last.pnl : undefined;
  return (
    <div>
      <div className="flex items-end gap-4">
        <div className="shrink-0">
          <div className="label">Equity</div>
          <div className="num mt-1 text-[26px] font-medium leading-none">{fmtUsd(equity)}</div>
        </div>
        {points && points.length > 1 && <Spark points={points} onHover={setHover} />}
      </div>
      {hover ? (
        <p className="num mt-2 text-[11px] text-ink-3">
          {fmtDateTime(hover.time)} · P&L <span className={tone(hover.pnl)}>{fmtUsd(hover.pnl, 2, true)}</span> · equity{" "}
          <span className="text-ink-2">{fmtUsd(hover.equity)}</span>
        </p>
      ) : (
        last &&
        putIn != null && (
          <p className="mt-2 text-[11px] text-ink-3">
            <span className={tone(last.pnl)}>
              {arrow(last.pnl)} {last.pnl < 0 ? `Burned ${fmtUsd(-last.pnl)}` : `Up ${fmtUsd(last.pnl)}`}
            </span>{" "}
            {last.pnl < 0 ? "of" : "on"} {fmtUsd(putIn)} put in ({fmtPct(last.pnl / putIn)}) since{" "}
            {new Date(points![0].time).toISOString().slice(0, 10)}
          </p>
        )
      )}
    </div>
  );
}

function Spark({ points, onHover }: { points: BurnPoint[]; onHover: (p?: BurnPoint) => void }) {
  const el = useRef<SVGSVGElement>(null);
  const [w, setW] = useState(0);
  const [at, setAt] = useState<number>();
  const id = useId();
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el.current!);
    return () => ro.disconnect();
  }, []);

  const t0 = points[0].time;
  const span = points.at(-1)!.time - t0 || 1;
  const lo = Math.min(0, ...points.map((p) => p.pnl));
  const hi = Math.max(0, ...points.map((p) => p.pnl));
  const x = (t: number) => PAD + ((t - t0) / span) * (w - 2 * PAD);
  const y = (v: number) => PAD + ((hi - v) / (hi - lo || 1)) * (H - 2 * PAD);
  const zero = hi === lo ? H / 2 : y(0);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.time)},${hi === lo ? zero : y(p.pnl)}`).join("");
  const area = `${line}L${x(points.at(-1)!.time)},${zero}L${x(t0)},${zero}Z`;

  const move = (e: PointerEvent) => {
    const t = t0 + ((e.clientX - el.current!.getBoundingClientRect().left - PAD) / (w - 2 * PAD)) * span;
    const i = points.reduce((best, p, j) => (Math.abs(p.time - t) < Math.abs(points[best].time - t) ? j : best), 0);
    setAt(i);
    onHover(points[i]);
  };
  const leave = () => {
    setAt(undefined);
    onHover(undefined);
  };
  const p = at != null ? points[at] : undefined;
  return (
    <svg
      ref={el}
      height={H}
      className="min-w-0 flex-1 cursor-crosshair"
      onPointerMove={move}
      onPointerLeave={leave}
      role="img"
      aria-label="all-time P&L"
    >
      {w > 0 && (
        <>
          <clipPath id={`${id}up`}>
            <rect x={0} y={0} width={w} height={zero} />
          </clipPath>
          <clipPath id={`${id}dn`}>
            <rect x={0} y={zero} width={w} height={H - zero} />
          </clipPath>
          <line x1={0} x2={w} y1={zero} y2={zero} className="stroke-ink-3" strokeWidth={1} strokeDasharray="2 3" />
          <g clipPath={`url(#${id}up)`} className="fill-up/15 stroke-up">
            <path d={area} stroke="none" />
            <path d={line} fill="none" strokeWidth={2} strokeLinejoin="round" />
          </g>
          <g clipPath={`url(#${id}dn)`} className="fill-down/15 stroke-down">
            <path d={area} stroke="none" />
            <path d={line} fill="none" strokeWidth={2} strokeLinejoin="round" />
          </g>
          {p && (
            <>
              <line x1={x(p.time)} x2={x(p.time)} y1={0} y2={H} className="stroke-ink-3" strokeWidth={1} />
              <circle
                cx={x(p.time)}
                cy={hi === lo ? zero : y(p.pnl)}
                r={4}
                className={`${p.pnl < 0 ? "fill-down" : "fill-up"} stroke-panel`}
                strokeWidth={2}
              />
            </>
          )}
        </>
      )}
    </svg>
  );
}
