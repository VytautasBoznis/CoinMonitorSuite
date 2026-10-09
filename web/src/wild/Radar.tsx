import { useEffect, useRef, type RefObject } from "react";

import { fmtPct } from "../format";
import type { CoinView } from "./model";

export type Ripple = { coin: string; usd: number; longs: boolean; born: number };

const CYAN = [0, 229, 255];
const AMBER = [255, 176, 0];
const RED = [255, 51, 85];
const GREEN = [57, 255, 136];
const SWEEP_MS = 4000;
const RIPPLE_MS = 1700;

const rgba = (c: number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const mix = (a: number[], b: number[], t: number) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
/** cyan -> amber -> red as a coin closes in on its strike. */
export const heat = (p: number) => (p < 0.5 ? mix(CYAN, AMBER, p * 2) : mix(AMBER, RED, (p - 0.5) * 2));

/** The cascade radar. Each coin is a blip on its own bearing; its distance from the center is how
 *  much of the drop to its strike is still left this minute, so the center means "the bot buys".
 *  Liquidations ripple out of their coin's blip; whales shake the whole scope. */
export function Radar({ coins, ripples }: { coins: CoinView[]; ripples: RefObject<Ripple[]> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const data = useRef(coins);
  data.current = coins;

  useEffect(() => {
    const el = canvas.current!;
    const ctx = el.getContext("2d")!;
    let size = 0;
    const fit = () => {
      const r = el.getBoundingClientRect();
      size = Math.min(r.width, r.height);
      const dpr = window.devicePixelRatio || 1;
      el.width = r.width * dpr;
      el.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    fit();

    let raf = 0;
    const draw = (now: number) => {
      raf = requestAnimationFrame(draw);
      const w = el.width / (window.devicePixelRatio || 1);
      const h = el.height / (window.devicePixelRatio || 1);
      const cx = w / 2;
      const cy = h / 2;
      const R = size / 2 - 46;
      if (R <= 40) return;
      ctx.clearRect(0, 0, w, h);

      // scope glass
      const glass = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.05);
      glass.addColorStop(0, "rgba(0,229,255,0.10)");
      glass.addColorStop(0.7, "rgba(0,229,255,0.03)");
      glass.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = glass;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.05, 0, Math.PI * 2);
      ctx.fill();

      // rings: the share of the drop already travelled
      ctx.font = "600 9px 'JetBrains Mono Variable', monospace";
      ctx.textAlign = "left";
      for (let k = 1; k <= 4; k++) {
        ctx.beginPath();
        ctx.arc(cx, cy, (R * k) / 4, 0, Math.PI * 2);
        ctx.strokeStyle = rgba(CYAN, k === 4 ? 0.45 : 0.16);
        ctx.lineWidth = k === 4 ? 1.5 : 1;
        ctx.setLineDash(k === 4 ? [] : [3, 5]);
        ctx.stroke();
        ctx.setLineDash([]);
        if (k < 4) {
          ctx.fillStyle = rgba(CYAN, 0.45);
          ctx.fillText(`${100 - k * 25}%`, cx + 4, cy - (R * k) / 4 - 3);
        }
      }
      // compass ticks
      for (let d = 0; d < 360; d += 5) {
        const a = (d * Math.PI) / 180;
        const len = d % 30 === 0 ? 10 : 4;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
        ctx.lineTo(cx + Math.cos(a) * (R + len), cy + Math.sin(a) * (R + len));
        ctx.strokeStyle = rgba(CYAN, d % 30 === 0 ? 0.5 : 0.2);
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // the strike zone
      const pulse = 0.5 + 0.5 * Math.sin(now / 300);
      const zone = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.12);
      zone.addColorStop(0, rgba(RED, 0.55 + 0.25 * pulse));
      zone.addColorStop(1, rgba(RED, 0));
      ctx.fillStyle = zone;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.12, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = rgba(RED, 0.95);
      ctx.textAlign = "center";
      ctx.font = "800 9px 'Orbitron Variable', monospace";
      ctx.fillText("STRIKE", cx, cy + 3);

      // the sweep
      const sweep = ((now % SWEEP_MS) / SWEEP_MS) * Math.PI * 2 - Math.PI / 2;
      const trail = ctx.createConicGradient(sweep - 1.1, cx, cy);
      trail.addColorStop(0, rgba(CYAN, 0));
      trail.addColorStop(0.175, rgba(CYAN, 0.28));
      trail.addColorStop(0.176, rgba(CYAN, 0));
      ctx.fillStyle = trail;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, R, sweep - 1.1, sweep);
      ctx.closePath();
      ctx.fill();
      ctx.save();
      ctx.shadowColor = rgba(CYAN, 1);
      ctx.shadowBlur = 14;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(sweep) * R, cy + Math.sin(sweep) * R);
      ctx.strokeStyle = rgba(CYAN, 0.95);
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();

      // blips
      const list = data.current;
      const pos = new Map<string, [number, number]>();
      list.forEach((c, i) => {
        const a = -Math.PI / 2 + (i * Math.PI * 2) / list.length;
        const r = Math.max(0.12, 0.9 * (1 - c.p)) * R; // 0.9: calm blips sit inside the rim, clear of the labels
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        pos.set(c.coin, [x, y]);

        // bearing line and label at the rim
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
        ctx.strokeStyle = rgba(CYAN, 0.08);
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.font = "800 12px 'Orbitron Variable', monospace";
        ctx.textAlign = "center";
        ctx.fillStyle = rgba(CYAN, 0.9);
        ctx.fillText(c.coin, cx + Math.cos(a) * (R + 30), cy + Math.sin(a) * (R + 30) + 4);

        const since = (((sweep - a) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
        const lit = Math.exp(-since * 1.6);
        const col = c.state === "trade" ? GREEN : heat(c.p);
        const hot = c.p > 0.8 ? 0.5 + 0.5 * Math.sin(now / 80) : 0;

        ctx.save();
        ctx.shadowColor = rgba(col, 1);
        ctx.shadowBlur = 10 + 26 * Math.max(lit, hot);
        ctx.fillStyle = rgba(col, 0.55 + 0.45 * Math.max(lit, hot));
        ctx.beginPath();
        ctx.arc(x, y, 5 + 4 * Math.max(lit, hot), 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        if (c.state === "trade") {
          // a locked-on reticle that spins
          const spin = now / 600;
          ctx.strokeStyle = rgba(GREEN, 0.95);
          ctx.lineWidth = 2;
          for (let q = 0; q < 4; q++) {
            ctx.beginPath();
            ctx.arc(x, y, 17, spin + (q * Math.PI) / 2, spin + (q * Math.PI) / 2 + 0.7);
            ctx.stroke();
          }
          ctx.font = "800 9px 'Orbitron Variable', monospace";
          ctx.fillStyle = rgba(GREEN, 1);
          ctx.fillText("LOCKED", x, y - 24);
        } else if (c.p > 0.8) {
          ctx.beginPath();
          ctx.arc(x, y, 14 + 10 * hot, 0, Math.PI * 2);
          ctx.strokeStyle = rgba(RED, 0.8 * hot);
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        ctx.font = "600 10px 'JetBrains Mono Variable', monospace";
        ctx.fillStyle = rgba(col, 0.95);
        ctx.fillText(c.drop != null ? fmtPct(c.drop) : "—", x, y + 20);
      });

      // liquidation ripples, from the coin's blip
      const live = ripples.current;
      for (let i = live.length - 1; i >= 0; i--) {
        const rp = live[i];
        const age = (now - rp.born) / RIPPLE_MS;
        if (age >= 1) {
          live.splice(i, 1);
          continue;
        }
        const at = pos.get(rp.coin);
        if (!at) continue;
        const k = Math.min(1, Math.log10(Math.max(rp.usd, 10)) / 6);
        const col = rp.longs ? RED : CYAN;
        ctx.beginPath();
        ctx.arc(at[0], at[1], 6 + age * (20 + 70 * k), 0, Math.PI * 2);
        ctx.strokeStyle = rgba(col, (1 - age) * 0.9);
        ctx.lineWidth = 1 + 3 * k * (1 - age);
        ctx.stroke();
        if (rp.usd >= 100_000) {
          ctx.beginPath();
          ctx.arc(cx, cy, age * R * 1.25, 0, Math.PI * 2);
          ctx.strokeStyle = rgba(RED, (1 - age) * 0.6);
          ctx.lineWidth = 6 * (1 - age);
          ctx.stroke();
        }
      }
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [ripples]);

  return <canvas ref={canvas} className="absolute inset-0 h-full w-full" />;
}
