import { useState } from "react";

import type { BotState } from "../api";
import { fmtDur } from "../format";
import { useHoldToFire } from "../hooks";
import { Panel } from "./Panel";

const DRAIN_OPTIONS = [30, 60, 90, 120];
const label = (m: number) => (m >= 120 ? `${m / 60}h` : `${m}m`);

/** Fires only after a continuous 1s press (pointer, Space or Enter). Letting go cancels. */
function PanicButton({ enabled, onFire }: { enabled: boolean; onFire: () => Promise<void> }) {
  const { progress, busy, handlers } = useHoldToFire(onFire, enabled);
  return (
    <button
      disabled={!enabled || busy}
      {...handlers}
      className="relative h-12 w-full touch-none select-none overflow-hidden rounded-[4px] border border-down/70 bg-down/10 text-[12px] font-bold tracking-[0.18em] text-down transition-colors hover:bg-down/15 disabled:cursor-not-allowed disabled:border-line disabled:bg-panel-2 disabled:text-ink-3"
    >
      <span className="absolute inset-y-0 left-0 bg-down/40" style={{ width: `${progress * 100}%` }} />
      <span className="relative">{busy ? "FLATTENING…" : progress > 0 ? "KEEP HOLDING…" : "■  HOLD TO PANIC"}</span>
    </button>
  );
}

export function Controls({
  state,
  keyed,
  now,
  onPanic,
  onDrain,
}: {
  state?: BotState;
  keyed: boolean;
  now: number;
  onPanic: () => Promise<void>;
  onDrain: (minutes: number) => Promise<void>;
}) {
  const [minutes, setMinutes] = useState(90);
  const [busy, setBusy] = useState(false);
  const live = state?.db ? state : undefined;
  const canDrain = live?.mode === "RUN";

  return (
    <Panel title="Kill switch" className="flex-1">
      <div className="space-y-4 p-3">
        <div>
          <PanicButton enabled={keyed} onFire={onPanic} />
          <p className="mt-1.5 text-[11px] leading-snug text-ink-3">
            {keyed ? (
              "Cancel every order, close every position at market, halt. Works with the bot dead."
            ) : (
              <>
                No agent key in the dashboard's env. Run <code className="text-ink-2">coinmon stop --now</code>.
              </>
            )}
          </p>
        </div>

        <div>
          <div className="mb-1.5 flex gap-1">
            {DRAIN_OPTIONS.map((m) => (
              <button
                key={m}
                onClick={() => setMinutes(m)}
                className={`num flex-1 rounded-[3px] py-1 text-[11px] ${
                  m === minutes ? "bg-panel-2 text-ink" : "text-ink-3 hover:text-ink-2"
                }`}
              >
                {label(m)}
              </button>
            ))}
          </div>
          <button
            disabled={!canDrain || busy}
            onClick={async () => {
              setBusy(true);
              await onDrain(minutes).finally(() => setBusy(false));
            }}
            className="h-10 w-full rounded-[4px] border border-warn/60 bg-warn/10 text-[12px] font-bold tracking-[0.18em] text-warn transition-colors hover:bg-warn/15 disabled:cursor-not-allowed disabled:border-line disabled:bg-panel-2 disabled:text-ink-3"
          >
            DRAIN · {label(minutes)}
          </button>
          <p className="mt-1.5 text-[11px] leading-snug text-ink-3">
            {live?.mode === "DRAIN" && live.deadline_ms != null ? (
              <>
                Draining: no new bids, exits working. Flat at market in{" "}
                <span className="num text-warn">{fmtDur(live.deadline_ms - now)}</span>.
              </>
            ) : (
              "Planned downtime: no new bids, exits keep working, flatten at market at the deadline."
            )}
          </p>
          {live?.mode === "DRAIN" && live.heartbeat !== "alive" && (
            <p className="mt-2 rounded-[3px] bg-warn/10 px-2 py-1.5 text-[11px] text-warn">
              ⚠ The bot is not running, so nothing is draining. Run <code>coinmon stop --drain</code>.
            </p>
          )}
        </div>

        <p className="border-t border-line pt-3 text-[11px] text-ink-3">
          Resume is CLI-only: <code className="text-ink-2">coinmon bot resume</code>
        </p>
      </div>
    </Panel>
  );
}
