export type Toast = { id: number; kind: "ok" | "warn" | "error"; text: string; sticky?: boolean };

const LOOK = {
  ok: "border-up/50 text-up",
  warn: "border-warn/50 text-warn",
  error: "border-down/60 text-down",
};
const ICON = { ok: "✓", warn: "⚠", error: "✕" };

export function Toasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed right-4 top-14 z-50 flex w-[380px] flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`slide-in pointer-events-auto flex items-start gap-3 rounded-[4px] border bg-panel-2 px-3 py-2.5 text-[12px] shadow-2xl shadow-black/50 ${LOOK[t.kind]}`}
        >
          <span className="font-bold">{ICON[t.kind]}</span>
          <span className="flex-1 text-ink">{t.text}</span>
          <button onClick={() => dismiss(t.id)} className="text-ink-3 hover:text-ink" aria-label="dismiss">
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
