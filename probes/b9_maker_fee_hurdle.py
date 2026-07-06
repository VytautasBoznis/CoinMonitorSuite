"""Plan-B probe B9 — did the FEE hurdle, not signal absence, kill the families? (plan-b §P3).

Hypothesis: the price-shape families all died on the taker round-trip. If the SAME persisted GO
genomes turn expectancy-positive once they pay a maker fee and fill as resting limit orders, the
cost floor — not the absence of signal — is what beat them, and an honest maker-execution model
(chunk Z3) is worth building.

Frozen rule (plan-b §P3, informational — NO PASS/FAIL): per candidate, pool its strictly-OOS
trade ledger twice with IDENTICAL eval-pairs —
  * baseline : taker fee (config 10 bps) + IdealExecution (fill at next open, always)
  * maker    : 2 bps maker fee + MakerLimitExecution (rest a limit at the prior close; fill only
               if the bar trades through it, else the trade is skipped)
and report the per-candidate expectancy delta. The plan funds Z3 if >= 5 of 10 flip
expectancy-positive. [[ga-parked]] bans the GA that B9's original "top-10 by t_exp" clause needs
to rank, so this runs GA-FREE on the persisted GO winners instead (informational, not the literal
top-10). MakerLimitExecution is optimistic (ignores queue position + adverse selection), so a
maker 'edge' here funds infrastructure only, never a certificate.

The winners were trained on Bybit USDT (universe auto-built from the stored USDT legs), so run with
that quote/venue. Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  COINMON_EXCHANGE=bybit COINMON_QUOTE_CURRENCY=USDT \
  .venv/Scripts/python probes/b9_maker_fee_hurdle.py
"""
from __future__ import annotations

import json

import pandas as pd

from coinmon.backtest.execution import MakerLimitExecution
from coinmon.cli import _funding_reader, _genome_from_spec
from coinmon.config import settings
from coinmon.data import db
from coinmon.search.evidence import pool_trades, select_eval_pairs
from coinmon.search.runner import discover_universe

# The persisted GO winners from the certified sweeps, with the timeframe each was searched on.
GO_FILES = [
    ("runs/go_winners_usdt.json", "1d"),
    ("runs/go_winners_usdt_1d_heavy.json", "1d"),
    ("runs/go_winners_usdt_4h.json", "4h"),
]

TAKER_FEE = settings.taker_fee   # config 10 bps baseline (taker on both legs)
MAKER_FEE = 0.0002               # Bybit VIP0 maker, per user 2026-07-06 (config placeholder is 10 bps)
EVAL_PAIRS = 8                   # same as `certify --eval-pairs` default
HOLDOUT = 0.2
SEED = 0


def _expectancy(trades) -> tuple[int, float]:
    """(#trades, mean net return per trade in %). Empty ledger -> (0, 0.0)."""
    if not trades:
        return 0, 0.0
    return len(trades), 100.0 * sum(t.net_return_pct for t in trades) / len(trades)


def main() -> None:
    conn = db.connect()
    funding = _funding_reader(conn)
    universes: dict[str, list[str]] = {}

    def read_at(tf: str):
        def read(symbol: str) -> pd.DataFrame:
            return db.read_candles(conn, settings.exchange, symbol, tf)
        return read

    print(f"B9 maker fee hurdle — GA-free on persisted GO winners "
          f"({settings.exchange} {settings.quote_currency})")
    print(f"baseline = taker {TAKER_FEE:.4f} + Ideal fill | maker = {MAKER_FEE:.4f} + limit fill\n")
    header = (f"{'family':<18}{'pair':<14}{'tf':>4}"
              f"{'N_tk':>6}{'exp_tk%':>10}{'N_mk':>6}{'exp_mk%':>10}{'d_exp':>9}  flip")
    print(header)
    print("-" * len(header))

    flips = 0
    total = 0
    for path, tf in GO_FILES:
        with open(path) as fh:
            specs = json.load(fh)
        read = read_at(tf)
        if tf not in universes:
            universes[tf] = discover_universe(
                db.list_series(conn), exchange=settings.exchange,
                quote=settings.quote_currency, timeframe=tf,
            )
        universe = universes[tf]
        for spec in specs:
            genome = _genome_from_spec(spec)
            eval_pairs = select_eval_pairs(
                genome, read, universe, EVAL_PAIRS, holdout_fraction=HOLDOUT, seed=SEED,
            )
            taker = pool_trades(
                genome, read, TAKER_FEE, eval_pairs,
                holdout_fraction=HOLDOUT, read_funding=funding,
            )
            maker = pool_trades(
                genome, read, MAKER_FEE, eval_pairs,
                holdout_fraction=HOLDOUT, read_funding=funding,
                execution=MakerLimitExecution(),
            )
            n_tk, exp_tk = _expectancy(taker)
            n_mk, exp_mk = _expectancy(maker)
            flip = exp_tk <= 0.0 < exp_mk
            flips += flip
            total += 1
            print(f"{genome.family:<18}{genome.pair:<14}{tf:>4}"
                  f"{n_tk:>6}{exp_tk:>10.3f}{n_mk:>6}{exp_mk:>10.3f}"
                  f"{exp_mk - exp_tk:>9.3f}  {'*' if flip else ''}")

    conn.close()
    print(f"\nB9 (informational): {flips}/{total} GO winners flip expectancy-positive under maker "
          f"execution. Frozen rule funds Z3 (honest maker model) at >= 5/10; here the denominator "
          f"is {total} persisted GO winners (GA banned, so no top-10 ranking).")


if __name__ == "__main__":
    main()
