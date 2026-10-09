// Number and time formatting. Every number on screen goes through here (mono, tabular).

const MINUS = "−";

export function decimals(px: number): number {
  const a = Math.abs(px);
  return a >= 10_000 ? 1 : a >= 1_000 ? 2 : a >= 10 ? 3 : a >= 1 ? 4 : a >= 0.1 ? 5 : 6;
}

export function fmtPx(px: number | null | undefined, dp?: number): string {
  if (px == null || !Number.isFinite(px)) return "—";
  const d = dp ?? decimals(px);
  return px.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function fmtUsd(v: number | null | undefined, dp = 2, signed = false): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v < 0 ? MINUS : signed && v > 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
}

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });

export function fmtCompactUsd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v < 0 ? MINUS : ""}$${compact.format(Math.abs(v))}`;
}

export function fmtPct(v: number | null | undefined, dp = 2, signed = true): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v < 0 ? MINUS : signed && v > 0 ? "+" : "";
  return `${sign}${Math.abs(v * 100).toFixed(dp)}%`;
}

/** "▲" / "▼" / "" — the non-color cue that rides along with up/down color. */
export const arrow = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲" : "▼");

export const tone = (v: number | null | undefined) =>
  v == null || v === 0 ? "text-ink-2" : v > 0 ? "text-up" : "text-down";

export function fmtClock(ms: number, seconds = true): string {
  return new Date(ms).toISOString().slice(11, seconds ? 19 : 16);
}

export function fmtDateTime(ms: number): string {
  const iso = new Date(ms).toISOString();
  return `${iso.slice(5, 10)} ${iso.slice(11, 19)}`;
}

export function fmtDur(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** Venue leverage text ("isolated 5") as "5× iso". */
export function fmtLev(lev: string): string {
  const [type, value] = lev.split(" ");
  return value ? `${value}× ${type === "isolated" ? "iso" : type}` : lev;
}

export function fmtAgo(ms: number | null | undefined, now: number): string {
  if (ms == null) return "never";
  const s = Math.max(0, (now - ms) / 1000);
  if (s < 90) return `${s.toFixed(0)}s`;
  if (s < 5400) return `${(s / 60).toFixed(0)}m`;
  if (s < 172_800) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86_400).toFixed(0)}d`;
}
