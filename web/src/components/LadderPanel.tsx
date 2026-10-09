import type { Account, Config, TradeRow } from "../api";
import { fmtDur, fmtLev, fmtPct, fmtPx, fmtUsd, tone } from "../format";
import { Chip, Panel } from "./Panel";

/** One row per coin: what the ladder has on the venue right now. */
export function LadderPanel({
  coins,
  unlisted,
  venue,
  account,
  trades,
  mids,
  rule,
  now,
}: {
  coins: string[];
  unlisted: string[];
  venue: string;
  account?: Account;
  trades?: TradeRow[];
  mids: Record<string, number>;
  rule: Config["rule"];
  now: number;
}) {
  return (
    <Panel
      title="Ladder"
      right={
        <span className="num text-[11px] text-ink-3">
          −{(rule.drop * 100).toFixed(1)}% · TP +{(rule.target * 100).toFixed(1)}% · {rule.hold_ms / 60_000}m
        </span>
      }
    >
      <div className="divide-y divide-line">
        {coins.map((coin) => (
          <Row key={coin} coin={coin} account={account} trades={trades} mid={mids[coin]} rule={rule} now={now} />
        ))}
      </div>
      {unlisted.length > 0 && (
        <div className="border-t border-line px-3 py-2 text-[11px] text-ink-3">
          {unlisted.join(", ")} not listed on {venue}: skipped.
        </div>
      )}
    </Panel>
  );
}

function Row({
  coin,
  account,
  trades,
  mid,
  rule,
  now,
}: {
  coin: string;
  account?: Account;
  trades?: TradeRow[];
  mid?: number;
  rule: Config["rule"];
  now: number;
}) {
  if (!account?.configured)
    return (
      <div className="flex items-center justify-between px-3 py-2.5">
        <span className="text-[13px] font-semibold">{coin}</span>
        <span className="text-[11px] text-ink-3">no account</span>
      </div>
    );
  const pos = account.positions.find((p) => p.coin === coin);
  const bid = account.orders.find((o) => o.coin === coin && o.side === "B" && !o.reduce_only);
  const tp = account.orders.find((o) => o.coin === coin && o.reduce_only);
  const open = trades?.find((t) => t.coin === coin && t.exit_ms == null);

  if (pos) {
    const left = open ? open.fill_ms + rule.hold_ms - now : undefined;
    const held = left != null ? 1 - left / rule.hold_ms : 0;
    return (
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold">{coin}</span>
          <Chip className="bg-up/15 text-up">▲ LONG</Chip>
          <span className="num text-[11px] text-ink-3">{fmtLev(pos.leverage)}</span>
          <span className={`num ml-auto text-[13px] ${tone(pos.upnl)}`}>{fmtUsd(pos.upnl, 2, true)}</span>
        </div>
        <div className="num mt-1.5 grid grid-cols-3 gap-2 text-[11px]">
          <span className="text-ink-3">
            IN <span className="text-ink">{fmtPx(pos.entry_px)}</span>
          </span>
          <span className="text-ink-3">
            TP <span className="text-up">{fmtPx(tp?.px)}</span>
          </span>
          <span className="text-ink-3">
            LIQ <span className="text-down">{fmtPx(pos.liq_px)}</span>
          </span>
        </div>
        {left != null && (
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-bg">
              <div className="h-full bg-warn/70" style={{ width: `${Math.min(100, held * 100)}%` }} />
            </div>
            <span className="num text-[10px] text-ink-3">out in {fmtDur(left)}</span>
          </div>
        )}
      </div>
    );
  }
  if (bid) {
    const dist = mid ? bid.px / mid - 1 : undefined;
    return (
      <div className="px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold">{coin}</span>
          <Chip className="bg-accent/15 text-accent">BID</Chip>
          <span className="num ml-auto text-[13px]">{fmtPx(bid.px)}</span>
        </div>
        <div className="num mt-1.5 flex justify-between text-[11px] text-ink-3">
          <span>
            <span className="text-ink-2">{fmtPct(dist)}</span> from mid
          </span>
          <span>{fmtUsd(bid.px * bid.sz)}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-3 py-2.5">
      <span className="text-[13px] font-semibold">{coin}</span>
      <Chip className="bg-panel-2 text-ink-3">IDLE</Chip>
      <span className="ml-auto text-[11px] text-ink-3">nothing resting</span>
    </div>
  );
}
