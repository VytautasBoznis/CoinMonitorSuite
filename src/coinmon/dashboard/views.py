"""Pure shaping for the dashboard API: bot heartbeat, trade ledger, liquidation buckets."""

from __future__ import annotations

import pandas as pd

from coinmon.live.control import Trade

STALE_S = 30  # a bot cycle is ~3s; no heartbeat for this long means the bot is not running
LONGS, SHORTS = "Buy", "Sell"  # Bybit's liquidation side is the liquidated position's side


def heartbeat_state(heartbeat_ms: int | None, ts_ms: int) -> str:
    """``alive``, ``stale`` or ``never``."""
    if heartbeat_ms is None:
        return "never"
    return "alive" if ts_ms - heartbeat_ms <= STALE_S * 1000 else "stale"


def ledger_rows(trades: list[Trade]) -> list[dict]:
    """One JSON row per round trip, in the frozen rule's terms (drop from anchor, hold, net)."""
    rows = []
    for t in trades:
        net = net_usd = None
        if t.exit_px is not None:
            net_usd = (t.exit_px - t.fill_px) * t.sz - t.entry_fee - t.exit_fee
            net = net_usd / (t.fill_px * t.sz)
        rows.append({
            "coin": t.coin, "entry_oid": t.entry_oid, "fill_ms": t.fill_ms, "sz": t.sz,
            "notional": t.fill_px * t.sz, "leverage": t.leverage, "liq_px": t.liq_px,
            "anchor_close": t.anchor_close, "fill_px": t.fill_px,
            "drop": t.fill_px / t.anchor_close - 1 if t.anchor_close else None,
            "tp_px": t.tp_px, "exit_px": t.exit_px, "exit_ms": t.exit_ms,
            "exit_reason": t.exit_reason, "exit_dir": t.exit_dir,
            "fees": t.entry_fee + (t.exit_fee or 0.0), "net": net, "net_usd": net_usd,
        })
    return rows


def ledger_summary(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["exit_ms"] is not None]
    priced = [r for r in closed if r["net_usd"] is not None]
    return {
        "open": len(rows) - len(closed),
        "closed": len(closed),
        "wins": sum(r["net_usd"] > 0 for r in priced),
        "realized_usd": sum(r["net_usd"] for r in priced),
        "fees_usd": sum(r["fees"] for r in rows),
    }


def coverage_gaps(spans: list[tuple[int, int]], start_ms: int, end_ms: int,
                  min_gap_ms: int = 60_000) -> list[tuple[int, int]]:
    """The parts of ``[start_ms, end_ms)`` no span covers, ignoring gaps under ``min_gap_ms``."""
    gaps, t = [], start_ms
    for a, b in sorted(spans):
        a = min(a, end_ms)
        if a - t >= min_gap_ms:
            gaps.append((t, a))
        t = max(t, b)
    if end_ms - t >= min_gap_ms:
        gaps.append((t, end_ms))
    return gaps


def liquidation_buckets(prints: pd.DataFrame, bucket_ms: int) -> list[dict]:
    """Liquidated notional (USD) per bucket: ``time`` (bucket open, ms), ``sell`` = longs
    liquidated (forced selling), ``buy`` = shorts liquidated (forced buying)."""
    if prints.empty:
        return []
    df = prints.assign(time=prints["ts"] // bucket_ms * bucket_ms,
                       notional=prints["price"] * prints["size"])
    wide = df.pivot_table(index="time", columns="side", values="notional", aggfunc="sum",
                          fill_value=0.0)
    return [
        {"time": int(t), "sell": float(r.get(LONGS, 0.0)), "buy": float(r.get(SHORTS, 0.0))}
        for t, r in wide.iterrows()
    ]
