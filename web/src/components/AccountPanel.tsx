import type { Account, Burn, Trades } from "../api";
import { fmtUsd, tone } from "../format";
import { EquityBurn } from "./EquityBurn";
import { Panel, Stat } from "./Panel";

export function AccountPanel({
  account,
  error,
  address,
  summary,
  burn,
}: {
  account?: Account;
  error?: string;
  address: string | null;
  summary?: Trades["summary"];
  burn?: Burn;
}) {
  const short = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : null;
  return (
    <Panel
      title="Account"
      right={
        error ? (
          <span className="text-[11px] text-down" title={error}>
            venue unreachable
          </span>
        ) : (
          short && <span className="num text-[11px] text-ink-3">{short}</span>
        )
      }
    >
      {!account ? (
        <div className="p-3 text-xs text-ink-3">loading…</div>
      ) : !account.configured ? (
        <div className="p-3 text-xs leading-relaxed text-ink-3">
          No wallet configured. Set <code className="text-ink-2">COINMON_HL_ADDRESS</code> to watch the account: positions,
          orders and equity are public by address, no key needed.
        </div>
      ) : (
        <AccountBody account={account} summary={summary} burn={burn} />
      )}
    </Panel>
  );
}

function AccountBody({
  account,
  summary,
  burn,
}: {
  account: Extract<Account, { configured: true }>;
  summary?: Trades["summary"];
  burn?: Burn;
}) {
  const upnl = account.positions.reduce((s, p) => s + p.upnl, 0);
  return (
    <div className="p-3">
      <EquityBurn equity={account.equity} points={burn?.configured ? burn.points : undefined} />
      <div className="mt-4 grid grid-cols-3 gap-x-3 gap-y-3">
        <Stat label="uPnL">
          <span className={tone(upnl)}>{fmtUsd(upnl, 2, true)}</span>
        </Stat>
        <Stat label="Realized">
          <span className={tone(summary?.realized_usd)}>{fmtUsd(summary?.realized_usd, 2, true)}</span>
        </Stat>
        <Stat label="Fees paid">{fmtUsd(summary?.fees_usd)}</Stat>
        <Stat label="Margin">{fmtUsd(account.margin_used)}</Stat>
        <Stat label="Withdrawable">{fmtUsd(account.withdrawable)}</Stat>
        <Stat label="Wins">
          {summary ? `${summary.wins}/${summary.closed}` : "—"}
        </Stat>
      </div>
    </div>
  );
}
