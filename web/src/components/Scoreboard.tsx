import { useEffect } from "react";

import type { TradeRow } from "../api";
import { arrow, fmtPct, fmtUsd, tone } from "../format";
import { GRAVES, HURDLE, STANDING, WINNERS_NEEDED, type Standing } from "../strategies";
import { Chip } from "./Panel";

const LOOK: Record<Standing["status"], string> = {
  LIVE: "bg-up/15 text-up",
  CERTIFIED: "bg-accent/15 text-accent",
  PARKED: "bg-panel-2 text-ink-2",
  LEAD: "bg-warn/15 text-warn",
};

/** Every idea taken through a probe: what is still standing (the live book scored against its
 *  backtest) and the graveyard, each grave with the number that killed it. Esc closes. */
export function Scoreboard({ trades, onClose }: { trades?: TradeRow[]; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 overflow-y-auto bg-bg/97 backdrop-blur-sm">
      <div className="mx-auto max-w-[1560px] px-8 pb-12 pt-6">
        <header className="flex items-start gap-6">
          <div>
            <h1 className="text-[13px] font-bold tracking-[0.2em]">SCOREBOARD &amp; GRAVEYARD</h1>
            <p className="mt-1.5 text-[12px] text-ink-2">
              Deployable winners: <span className="num text-ink">0</span> of the{" "}
              <span className="num text-ink">{WINNERS_NEEDED}</span> the mission needs. {GRAVES.length} ideas buried, {STANDING.length}{" "}
              still standing.
            </p>
            <p className="mt-0.5 text-[12px] text-ink-3">{HURDLE}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-auto rounded-[3px] border border-line px-2.5 py-1 text-[11px] font-semibold tracking-[0.12em] text-ink-2 hover:bg-panel-2 hover:text-ink"
          >
            ✕ CLOSE
          </button>
        </header>

        <h2 className="label mt-7">Still standing</h2>
        <div className="mt-2 grid grid-cols-4 gap-2">
          {STANDING.map((s) => (
            <article key={s.id} className="flex flex-col border border-line bg-panel p-4">
              <div className="flex items-center gap-2">
                <span className="num text-[11px] text-ink-3">{s.id}</span>
                <span className="text-[14px] font-semibold">{s.name}</span>
                <Chip className={`ml-auto ${LOOK[s.status]}`}>{s.status}</Chip>
              </div>
              <p className="mt-2 text-[12px] leading-snug text-ink-2">{s.what}</p>
              <p className="mt-2 text-[12px] leading-snug text-ink">{s.evidence}</p>
              {s.backtest && <LiveScore trades={trades} backtest={s.backtest} />}
              <p className="mt-auto pt-3 text-[11px] leading-snug text-ink-3">
                <span className="text-warn">Why not deployed:</span> {s.blocker}
              </p>
              <p className="num mt-2 text-[10px] text-ink-3">since {s.since}</p>
            </article>
          ))}
        </div>

        <h2 className="label mt-8">Graveyard</h2>
        <div className="mt-2 grid grid-cols-3 gap-2 2xl:grid-cols-4">
          {GRAVES.map((g) => (
            <article key={g.id} className="flex flex-col border border-line bg-panel p-4">
              <div className="flex items-baseline gap-2">
                <span className="text-ink-3">☠</span>
                <span className="text-[13px] font-semibold text-ink-2">{g.name}</span>
                <span className="num ml-auto text-[10px] text-ink-3">
                  {g.id} · {g.died}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-snug text-ink-3">{g.what}</p>
              <p className="mt-2 text-[12px] leading-snug text-ink-2">{g.cause}</p>
              <p className="mt-auto pt-3 text-[12px] italic text-ink-3">“{g.epitaph}”</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The live book against its backtest, from the bot's own ledger. */
function LiveScore({ trades, backtest }: { trades?: TradeRow[]; backtest: NonNullable<Standing["backtest"]> }) {
  const closed = (trades ?? []).filter((t) => t.net != null);
  const mean = closed.length ? closed.reduce((s, t) => s + t.net!, 0) / closed.length : null;
  const hits = closed.filter((t) => t.exit_reason === "tp").length;
  const usd = closed.reduce((s, t) => s + t.net_usd!, 0);
  return (
    <div className="num mt-3 grid grid-cols-3 gap-3 rounded-[3px] bg-bg px-3 py-2.5 text-[11px]">
      <div>
        <div className="label">Live fills</div>
        <div className="mt-1 text-[13px]">{closed.length}</div>
        <div className={`mt-0.5 ${tone(usd)}`}>{fmtUsd(usd, 2, true)}</div>
      </div>
      <div>
        <div className="label">Per event</div>
        <div className={`mt-1 text-[13px] ${tone(mean)}`}>
          {arrow(mean)} {fmtPct(mean)}
        </div>
        <div className="mt-0.5 text-ink-3">backtest {fmtPct(backtest.perEvent)}</div>
      </div>
      <div>
        <div className="label">Target hit</div>
        <div className="mt-1 text-[13px]">{closed.length ? `${hits}/${closed.length}` : "—"}</div>
        <div className="mt-0.5 text-ink-3">backtest {fmtPct(backtest.targetHit, 1, false)}</div>
      </div>
    </div>
  );
}
