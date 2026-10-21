import { useEffect, type ReactNode } from "react";

import { api, type Baseline, type Bot, type Card } from "../api";
import { arrow, fmtDate, fmtPct, fmtRule, fmtUsd, tone } from "../format";
import { usePoll } from "../hooks";
import { GRAVES, HURDLE, STANDING, WINNERS_NEEDED, type Standing } from "../strategies";
import { Chip } from "./Panel";

const LOOK: Record<Standing["status"], string> = {
  LIVE: "bg-up/15 text-up",
  CERTIFIED: "bg-accent/15 text-accent",
  PARKED: "bg-panel-2 text-ink-2",
  LEAD: "bg-warn/15 text-warn",
};
const MIN_N = 50; // the bar's minimum sample (src/coinmon/live/score.py)

/** Every idea taken through a probe: the bots forward-testing now (each scored against its own
 *  frozen backtest), what is still standing, and the graveyard, each grave with the number that
 *  killed it. Esc closes. */
export function Scoreboard({ bots, onClose }: { bots?: Bot[]; onClose: () => void }) {
  const cards = usePoll(api.scoreboard, 30_000);
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

        <h2 className="label mt-7">Forward tests</h2>
        <p className="mt-1 text-[12px] text-ink-3">
          Each bot against its own backtest, frozen before it ran (last 2 years, the same 6 coins, Hyperliquid fees). Not ranked: a
          paper bot gets money only by the bar written before it started.
          {cards.error && <span className="text-down"> Scores unavailable: {cards.error}</span>}
        </p>
        <div className="mt-2 grid grid-cols-4 gap-2">
          {bots?.map((b) => (
            <Forward key={b.id} bot={b} card={cards.data?.find((c) => c.id === b.id)} />
          ))}
        </div>

        <h2 className="label mt-8">Still standing</h2>
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

const ci = (c: [number, number] | null | undefined) => (c ? `${fmtPct(c[0]).slice(0, -1)} to ${fmtPct(c[1])}` : "—");
const perYear = (v: number | null | undefined) => (v == null ? "—" : `${fmtPct(v, 1)}/yr`);

/** One bot's forward record next to its frozen backtest, with its verdict in plain words. */
function Forward({ bot, card }: { bot: Bot; card?: Card }) {
  return (
    <article className="flex flex-col border border-line bg-panel p-4">
      <div className="flex items-center gap-2">
        <span className="text-[14px] font-semibold">{bot.id}</span>
        <Chip className={bot.paper ? "bg-accent/15 text-accent" : "bg-down/15 text-down"}>{bot.paper ? "PAPER" : "LIVE"}</Chip>
        {card && <Badge card={card} />}
      </div>
      <p className="num mt-1 text-[11px] text-ink-3">{fmtRule(bot.rule)}</p>
      <p className="mt-2 text-[12px] leading-snug text-ink-2">{bot.question}</p>
      {card ? <Record card={card} base={bot.baseline} /> : <p className="mt-3 text-[11px] text-ink-3">loading…</p>}
      {card?.capture && (
        <p className="num mt-2 rounded-[3px] bg-bg px-3 py-2 text-[11px] leading-snug text-ink-2">
          {card.capture.twin === 0 ? (
            "No twin fills yet to hold against the live bot's."
          ) : (
            <>
              Live bot got <span className="text-ink">{card.capture.caught}</span> of the twin's{" "}
              <span className="text-ink">{card.capture.twin}</span> fills, plus {card.capture.live_only} the twin didn't. Live − paper:{" "}
              <span className={tone(card.capture.gap)}>{fmtPct(card.capture.gap)}</span>/trip (n {card.capture.n_gap}).
            </>
          )}
        </p>
      )}
      <p className="mt-auto pt-3 text-[11px] leading-snug text-ink-3">{card && plain(card)}</p>
      <p className="num mt-2 text-[10px] text-ink-3">{card?.since_ms ? `since ${fmtDate(card.since_ms)}` : "not started"}</p>
    </article>
  );
}

function Record({ card, base }: { card: Card; base: Baseline }) {
  const row = (label: string, fwd: ReactNode, bt: ReactNode) => (
    <>
      <span className="label self-center">{label}</span>
      <span className="text-right">{fwd}</span>
      <span className="text-right text-ink-3">{bt}</span>
    </>
  );
  const early = card.vs_backtest === "too early";
  return (
    <div className="num mt-3 grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-1.5 whitespace-nowrap rounded-[3px] bg-bg px-3 py-2.5 text-[11px]">
      <span />
      <span className="label text-right">Forward</span>
      <span className="label text-right">Backtest</span>
      {row(
        "Round trips",
        <>
          {card.n} <span className="text-ink-3">/ {card.expected_n.toFixed(1)} exp.</span>
        </>,
        `${base.per_year.toFixed(0)}/yr`,
      )}
      {row(
        "Per trip",
        <span className={early ? "text-ink-2" : tone(card.mean)}>
          {arrow(card.mean)} {fmtPct(card.mean)}
        </span>,
        fmtPct(base.mean),
      )}
      {row("95% CI", <span className="text-ink-2">{ci(card.ci)}</span>, ci(base.ci))}
      {row("Target hit", card.tp_hit == null ? "—" : fmtPct(card.tp_hit, 0, false), fmtPct(base.tp_hit, 1, false))}
      {row("Yield", <span className="text-ink-2">{perYear(card.yield_yr)}</span>, perYear(base.yield_yr))}
      {row("Net", <span className={tone(card.net_usd)}>{fmtUsd(card.net_usd, 2, true)}</span>, "")}
    </div>
  );
}

/** The headline: the bar's verdict for a bot that has one, else forward vs backtest. */
function Badge({ card }: { card: Card }) {
  const [look, text] = card.bar
    ? {
        "not started": ["bg-panel-2 text-ink-3", "NOT STARTED"],
        "too early": ["bg-panel-2 text-ink-2", "TOO EARLY"],
        extended: ["bg-warn/15 text-warn", "EXTENDED"],
        pass: ["bg-up/15 text-up", "▲ PASS"],
        fail: ["bg-down/15 text-down", "▼ FAIL"],
      }[card.bar.status]
    : {
        "too early": ["bg-panel-2 text-ink-2", "TOO EARLY"],
        "in line": ["bg-accent/15 text-accent", "IN LINE"],
        below: ["bg-down/15 text-down", "▼ BELOW BACKTEST"],
        above: ["bg-up/15 text-up", "▲ ABOVE BACKTEST"],
      }[card.vs_backtest];
  return <Chip className={`ml-auto ${look}`}>{text}</Chip>;
}

function plain(card: Card): string {
  const v = card.bar;
  if (v) {
    const on = v.at_ms ? fmtDate(v.at_ms) : "";
    if (v.status === "not started") return "Not started. The bar is judged once, 6 months after the first run.";
    if (v.status === "too early")
      return `Too early: ${card.n} of the ${MIN_N} round trips the bar needs. Judged once on ${on}: N ≥ ${MIN_N}, the CI clear of zero, ≥5%/yr.`;
    if (v.status === "extended") return `Under ${MIN_N} round trips at 6 months: one more look on ${on}, then retired.`;
    const record = `N ${v.n}, CI ${ci(v.ci)}, ${perYear(v.yield_yr)}`;
    return v.status === "pass"
      ? `PASSED on ${on} (${record}): earns F8-sized micro-live money from its own wallet.`
      : `FAILED on ${on} (${record}): retired.`;
  }
  return {
    "too early": `Too early: ${card.n} of the ${MIN_N} round trips before its CI says anything.`,
    "in line": "In line: the forward CI holds the backtest's mean.",
    below: "Below its backtest: the whole forward CI is under the backtest's mean.",
    above: "Above its backtest: the whole forward CI is over the backtest's mean.",
  }[card.vs_backtest];
}
