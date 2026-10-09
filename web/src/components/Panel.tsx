import type { ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`flex min-h-0 min-w-0 flex-col bg-panel ${className}`}>
      <header className="flex h-9 shrink-0 items-center justify-between gap-3 border-b border-line px-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-2">{title}</h2>
        {right}
      </header>
      <div className="min-h-0 flex-1">{children}</div>
    </section>
  );
}

export function Chip({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[3px] px-1.5 py-[3px] text-[10px] font-semibold leading-none tracking-[0.08em] ${className}`}
    >
      {children}
    </span>
  );
}

export function Dot({ className = "", live = false }: { className?: string; live?: boolean }) {
  return <span className={`inline-block size-1.5 rounded-full bg-current ${live ? "live-dot" : ""} ${className}`} />;
}

export function Stat({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="label">{label}</div>
      <div className="num mt-1 truncate text-[13px]">{children}</div>
    </div>
  );
}
