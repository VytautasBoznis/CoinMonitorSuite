import type { Config, Trades } from "../api";
import { arrow, fmtDateTime, fmtDur, fmtLev, fmtPct, fmtPx, fmtUsd, tone } from "../format";
import { Chip, Panel } from "./Panel";

const HEAD = ["Filled (UTC)", "Coin", "Size", "Notional", "Lev", "Anchor", "Fill", "Drop", "Exit", "Reason", "Hold", "Net", "Net $"];

/** The ledger: what the frozen rule assumed (anchor, -2.5% drop, 60m hold) next to what happened. */
export function FillsTable({ trades, rule, now }: { trades?: Trades; rule: Config["rule"]; now: number }) {
  const s = trades?.summary;
  return (
    <Panel
      title={`Fills${trades ? ` (${trades.rows.length})` : ""}`}
      right={
        s && (
          <span className="num text-[11px] text-ink-3">
            {s.closed} closed · {s.wins} won · realized{" "}
            <span className={tone(s.realized_usd)}>{fmtUsd(s.realized_usd, 2, true)}</span> · backtest +0.51%/event
          </span>
        )
      }
    >
      <div className="h-full overflow-auto">
        <table className="w-full border-collapse whitespace-nowrap text-[12px]">
          <thead className="sticky top-0 z-10 bg-panel">
            <tr>
              {HEAD.map((h, i) => (
                <th key={h} className={`label border-b border-line px-2 py-2 font-semibold ${i < 2 || i === 9 ? "text-left" : "text-right"}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="num">
            {trades?.rows.map((t) => {
              const open = t.exit_ms == null;
              return (
                <tr key={t.entry_oid} className="border-b border-line/60 hover:bg-panel-2">
                  <td className="px-2 py-1.5 text-ink-2">{fmtDateTime(t.fill_ms)}</td>
                  <td className="px-2 py-1.5 font-sans font-semibold">{t.coin}</td>
                  <td className="px-2 py-1.5 text-right">{t.sz}</td>
                  <td className="px-2 py-1.5 text-right">{fmtUsd(t.notional)}</td>
                  <td className="px-2 py-1.5 text-right text-ink-3">{fmtLev(t.leverage)}</td>
                  <td className="px-2 py-1.5 text-right text-ink-2">{fmtPx(t.anchor_close)}</td>
                  <td className="px-2 py-1.5 text-right">{fmtPx(t.fill_px)}</td>
                  <td className="px-2 py-1.5 text-right text-ink-2">{fmtPct(t.drop)}</td>
                  <td className="px-2 py-1.5 text-right">{fmtPx(t.exit_px)}</td>
                  <td className="px-2 py-1.5 font-sans">
                    {open ? (
                      <Chip className="bg-accent/15 text-accent">OPEN</Chip>
                    ) : (
                      <span className="text-[11px] uppercase tracking-wider text-ink-2" title={t.exit_dir ?? ""}>
                        {t.exit_reason}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-right text-ink-2">
                    {fmtDur((t.exit_ms ?? now) - t.fill_ms)}
                    {open && <span className="text-ink-3"> / {rule.hold_ms / 60_000}m</span>}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${tone(t.net)}`}>
                    {arrow(t.net)} {fmtPct(t.net)}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${tone(t.net_usd)}`}>{fmtUsd(t.net_usd, 2, true)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {trades && !trades.rows.length && (
          <div className="grid h-[calc(100%-36px)] place-items-center px-6 text-center text-[12px] text-ink-3">
            <div>
              <div className="text-ink-2">No fills yet.</div>
              <div className="mt-1">
                The ladder rests a bid {(rule.drop * 100).toFixed(1)}% under the prior 1m close and waits for a cascade.
              </div>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
