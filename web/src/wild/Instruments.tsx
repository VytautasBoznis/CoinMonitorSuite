import { useEffect, useRef, useState } from "react";

import { fmtCompactUsd } from "../format";
import { useHoldToFire } from "../hooks";
import { sfx } from "./sound";

/** One PQRST heartbeat, phase 0..1 -> amplitude. */
function beat(ph: number) {
  const g = (mu: number, s: number, a: number) => a * Math.exp(-((ph - mu) ** 2) / (2 * s * s));
  return g(0.18, 0.025, 0.12) - g(0.3, 0.008, 0.15) + g(0.32, 0.012, 1) - g(0.345, 0.01, 0.3) + g(0.55, 0.045, 0.25);
}

/** The bot's heartbeat as an ECG trace: beating while it cycles, a flatline when it is not. */
export function Ecg({ pulse }: { pulse: "alive" | "stale" | "never" | "down" }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const state = useRef(pulse);
  state.current = pulse;
  useEffect(() => {
    const el = canvas.current!;
    const ctx = el.getContext("2d")!;
    const dpr = window.devicePixelRatio || 1;
    const W = el.clientWidth;
    const H = el.clientHeight;
    el.width = W * dpr;
    el.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const ys = new Array<number>(W).fill(0);
    let last = performance.now();
    let x = 0;
    let raf = 0;
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const steps = Math.min(W, Math.round(((now - last) / 1000) * 90));
      if (steps <= 0) return;
      last = now;
      for (let s = 0; s < steps; s++) {
        const alive = state.current === "alive";
        ys[x] = alive ? beat(((now / 1000 - (steps - s) / 90) % 1.05) / 1.05) : (Math.random() - 0.5) * 0.02;
        x = (x + 1) % W;
      }
      const col = state.current === "alive" ? "57,255,136" : state.current === "never" ? "127,138,168" : "255,51,85";
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.shadowColor = `rgb(${col})`;
      ctx.shadowBlur = 8;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      for (let i = 0; i < W; i++) {
        const idx = (x + i) % W;
        const yy = H * 0.62 - ys[idx] * H * 0.55;
        if (i === 0) ctx.moveTo(i, yy);
        else ctx.lineTo(i, yy);
      }
      const fade = ctx.createLinearGradient(0, 0, W, 0);
      fade.addColorStop(0, `rgba(${col},0)`);
      fade.addColorStop(1, `rgba(${col},1)`);
      ctx.strokeStyle = fade;
      ctx.stroke();
      ctx.restore();
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={canvas} className="h-9 w-[200px]" />;
}

const LEVELS: [number, string, string][] = [
  [1e6, "ARMAGEDDON", "wr-glow-red"],
  [1e5, "CASCADE", "wr-glow-red"],
  [1e4, "HEATING UP", "wr-glow-amber"],
  [0, "CALM", "wr-glow-cyan"],
];

/** Forced selling in the last minute on a log needle ($1 .. $10M), plus a 5-minute sparkline. */
export function PressureGauge({ sell, buy, series }: { sell: number; buy: number; series: number[] }) {
  const k = Math.min(1, Math.log10(sell + 1) / 7);
  const angle = -90 + 180 * k;
  const [, label, glow] = LEVELS.find(([min]) => sell >= min)!;
  const peak = Math.max(1, ...series);
  return (
    <div className="flex flex-col items-center px-4 pb-3 pt-1">
      <svg viewBox="0 0 220 124" className="w-full max-w-[260px]">
        <defs>
          <linearGradient id="wr-arc" x1="0" x2="1">
            <stop offset="0" stopColor="#00e5ff" />
            <stop offset="0.55" stopColor="#ffb000" />
            <stop offset="1" stopColor="#ff3355" />
          </linearGradient>
          {/* user-space region: a glow on a straight line has a zero-width bbox and would vanish */}
          <filter id="wr-glow" filterUnits="userSpaceOnUse" x="-20" y="-20" width="260" height="170">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="rgb(127 138 168 / 0.15)" strokeWidth="12" />
        <path
          d="M 20 110 A 90 90 0 0 1 200 110"
          fill="none"
          stroke="url(#wr-arc)"
          strokeWidth="12"
          strokeDasharray={`${k * 283} 283`}
          filter="url(#wr-glow)"
        />
        {[0, 3, 4, 5, 6, 7].map((e) => {
          const a = ((-180 + (180 * e) / 7) * Math.PI) / 180;
          return (
            <g key={e}>
              <line x1={110 + Math.cos(a) * 76} y1={110 + Math.sin(a) * 76} x2={110 + Math.cos(a) * 84} y2={110 + Math.sin(a) * 84} stroke="rgb(0 229 255 / 0.5)" />
              <text x={110 + Math.cos(a) * 64} y={113 + Math.sin(a) * 64} fill="rgb(127 138 168)" fontSize="7" textAnchor="middle" fontFamily="JetBrains Mono Variable">
                {e === 0 ? "$0" : fmtCompactUsd(10 ** e)}
              </text>
            </g>
          );
        })}
        <g style={{ transform: `rotate(${angle}deg)`, transformOrigin: "110px 110px", transition: "transform 0.8s cubic-bezier(.2,1.6,.4,1)" }}>
          <line x1="110" y1="110" x2="110" y2="34" stroke="white" strokeWidth="2.5" filter="url(#wr-glow)" />
        </g>
        <circle cx="110" cy="110" r="6" fill="#ff2bd6" filter="url(#wr-glow)" />
      </svg>
      <div className={`wr-display -mt-1 text-[22px] font-black ${glow}`}>{fmtCompactUsd(sell)}</div>
      <div className={`wr-display text-[10px] font-bold tracking-[0.35em] ${glow}`}>{label}</div>
      <div className="mt-1 text-[10px] text-[var(--wr-dim)]">
        longs wiped, last 60s · shorts squeezed <span className="wr-glow-cyan">{fmtCompactUsd(buy)}</span>
      </div>
      <div className="mt-2 flex h-8 w-full items-end gap-[2px]" title="forced selling per 10s, last 5 min">
        {series.map((v, i) => (
          <div
            key={i}
            className="flex-1"
            style={{
              height: `${Math.max(4, (Math.log10(v + 1) / Math.log10(peak + 1)) * 100)}%`,
              background: v > 0 ? "var(--wr-red)" : "rgb(127 138 168 / 0.15)",
              boxShadow: v > 0 ? "0 0 6px var(--wr-red)" : undefined,
            }}
          />
        ))}
      </div>
    </div>
  );
}

/** A number whose digits roll like a mechanical counter. */
export function Odometer({ value, prefix = "$", decimals = 2 }: { value: number; prefix?: string; decimals?: number }) {
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return (
    <span className="inline-flex">
      {value < 0 ? "−" : ""}
      {prefix}
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={text.length - i} className="wr-odo-digit">
            <span className="wr-odo-strip" style={{ transform: `translateY(-${Number(ch) * 10}%)` }}>
              {"0123456789".split("").map((d) => (
                <span key={d}>{d}</span>
              ))}
            </span>
          </span>
        ) : (
          <span key={text.length - i}>{ch}</span>
        ),
      )}
    </span>
  );
}

/** PANIC as a launch button: lift the hazard cover, then hold the dome for a second. The cover drops
 *  back after 10s. Same ``onPanic`` as the terminal's button. */
export function LaunchPanic({ keyed, onPanic }: { keyed: boolean; onPanic: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => setOpen(false), 10_000);
    return () => window.clearTimeout(t);
  }, [open]);
  const { progress, busy, handlers } = useHoldToFire(async () => {
    await onPanic();
    setOpen(false);
  }, keyed && open);
  return (
    <div>
      <div className={`wr-launch ${open ? "open" : ""}`}>
        <button disabled={!keyed || !open || busy} className="wr-dome" style={{ ["--p" as string]: progress }} {...handlers}>
          {busy ? "…" : "PANIC"}
        </button>
        <div
          className="wr-cover"
          role="button"
          tabIndex={keyed ? 0 : -1}
          aria-label="lift the safety cover"
          onClick={() => {
            if (!keyed) return;
            sfx.arm();
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (keyed && (e.key === "Enter" || e.key === " ")) {
              e.preventDefault();
              sfx.arm();
              setOpen(true);
            }
          }}
        >
          <span>{keyed ? "LIFT COVER TO ARM" : "NO AGENT KEY"}</span>
        </div>
      </div>
      <div className="mt-2 text-center text-[10px] leading-relaxed text-[var(--wr-dim)]">
        {!keyed
          ? "no agent key in the dashboard env · use coinmon stop --now"
          : open
            ? "ARMED · hold the dome 1s to flatten everything · auto-closes in 10s"
            : "flatten everything at market · works with the bot dead"}
      </div>
    </div>
  );
}

export type Fx = { id: number; kind: "fill" | "win" | "loss" | "whale"; title: string; detail: string };

const SPARK = { fill: [0, 229, 255], win: [57, 255, 136], loss: [255, 176, 0], whale: [255, 51, 85] };

/** Full-screen moments: the bot bought, a position closed, or a whale got liquidated. */
export function FxOverlay({ fx }: { fx: Fx | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!fx || fx.kind === "whale") return;
    const el = canvas.current!;
    const ctx = el.getContext("2d")!;
    const W = (el.width = window.innerWidth);
    const H = (el.height = window.innerHeight);
    const col = SPARK[fx.kind];
    const parts = Array.from({ length: 220 }, () => {
      const a = Math.random() * Math.PI * 2;
      const v = 4 + Math.random() * 13;
      return { x: W / 2, y: H / 2, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 3, life: 1, size: 1 + Math.random() * 3 };
    });
    let raf = 0;
    const tick = () => {
      ctx.clearRect(0, 0, W, H);
      let alive = false;
      for (const p of parts) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.22;
        p.vx *= 0.985;
        p.life -= 0.012;
        if (p.life <= 0) continue;
        alive = true;
        ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${p.life})`;
        ctx.shadowColor = `rgb(${col[0]},${col[1]},${col[2]})`;
        ctx.shadowBlur = 10;
        ctx.fillRect(p.x, p.y, p.size * 2, p.size * 2);
      }
      if (alive) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [fx]);
  if (!fx) return null;
  return (
    <div key={fx.id} className={`wr-fx ${fx.kind}`}>
      <div className="wr-fx-flash" />
      {fx.kind !== "whale" && (
        <>
          <div className="wr-fx-ring" />
          <div className="wr-fx-ring r2" />
          <div className="wr-fx-ring r3" />
          <canvas ref={canvas} className="absolute inset-0" />
          <div className="wr-fx-text">
            <div className="wr-fx-title">{fx.title}</div>
            <div className="wr-fx-detail">{fx.detail}</div>
          </div>
        </>
      )}
      {fx.kind === "whale" && <div className="wr-fx-banner">{fx.title}</div>}
    </div>
  );
}
