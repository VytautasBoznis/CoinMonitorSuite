import { useEffect, useRef, useState } from "react";

import type { Bot } from "../api";
import { fmtRule } from "../format";
import { Chip, Dot } from "./Panel";

/** Dot color and a one-word status. A bot that never ran (paper before the swarm is deployed)
 *  is grey, not red: nothing failed. */
function health(b: Bot): { look: string; live: boolean; word: string } {
  const s = b.state;
  if (!s.db) return { look: "text-down", live: false, word: "db down" };
  if (s.heartbeat === "alive") return { look: s.mode === "RUN" ? "text-up" : "text-warn", live: true, word: s.mode.toLowerCase() };
  if (s.heartbeat === "never") return { look: "text-ink-3", live: false, word: "never ran" };
  return s.mode === "HALT" ? { look: "text-ink-3", live: false, word: "halted" } : { look: "text-down", live: false, word: "down" };
}

function Kind({ paper }: { paper: boolean }) {
  return <Chip className={paper ? "bg-accent/15 text-accent" : "bg-down/15 text-down"}>{paper ? "PAPER" : "LIVE"}</Chip>;
}

/** Which bot the terminal shows: the live bot or one of the swarm's paper bots. */
export function BotSwitch({ bots, selected, onSelect }: { bots: Bot[]; selected: Bot; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", away);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", away);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);
  const h = health(selected);
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-[3px] border border-line px-2 py-[5px] hover:bg-panel-2"
        title="switch bot"
      >
        <Dot className={h.look} live={h.live} />
        <span className="text-[12px] font-semibold tracking-[0.08em]">{selected.id.toUpperCase()}</span>
        <Kind paper={selected.paper} />
        <span className="text-[10px] text-ink-3">▾</span>
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-[380px] border border-line bg-panel shadow-[0_12px_32px_rgba(0,0,0,0.5)]">
          {bots.map((b) => {
            const bh = health(b);
            return (
              <button
                key={b.id}
                onClick={() => {
                  onSelect(b.id);
                  setOpen(false);
                }}
                className={`flex w-full items-start gap-2.5 border-b border-line/60 px-3 py-2.5 text-left hover:bg-panel-2 ${
                  b.id === selected.id ? "bg-panel-2" : ""
                }`}
              >
                <Dot className={`mt-[5px] ${bh.look}`} live={bh.live} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] font-semibold">{b.id}</span>
                    <Kind paper={b.paper} />
                    <span className={`ml-auto text-[10px] font-semibold uppercase tracking-wider ${bh.look}`}>{bh.word}</span>
                  </div>
                  <div className="num mt-1 text-[11px] text-ink-3">{fmtRule(b.rule)}</div>
                </div>
              </button>
            );
          })}
          <p className="px-3 py-2 text-[11px] leading-snug text-ink-3">
            Paper bots trade simulated fills on live Hyperliquid candles: no money. The kill switch always acts on the live bot.
          </p>
        </div>
      )}
    </div>
  );
}
