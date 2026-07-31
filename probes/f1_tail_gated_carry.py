"""F1 — TAIL-GATED funding carry: is the certified carry edge worth trading once the boring 95%
is amputated?

Pre-registered 2026-07-31, BEFORE running (rules frozen below). First probe of the Fable batch
([[fable-batch-10-probe-queue]]), ranked #1 by EV per hour of probe work and the highest-confidence
candidate on that list. Namespace: `f<N>_` = Fable-batch probe N, distinct from Plan-B `b<N>_`.

THE TRADE. Delta-neutral long spot / short perp on the same coin, entered ONLY when the trailing
3 funding prints annualize to >= +30%, exited when that trailing mean falls below +10% (hysteresis,
so a single cool print does not churn the book). This is W3 funding carry ([[w3-carry-first-live-
diagnosis]], CERTIFIED at +2.23%/yr but PARKED under the >=5%/yr live hurdle) with the flat 95% of
its life removed: sit in cash while carry is boring, deploy only into the manias.

WHY IT SHOULD PAY. Extreme positive funding is levered longs in hype alts bidding for exposure. The
premium persists because harvesting it needs spot inventory, tolerance for squeeze wicks against the
short leg, and exchange/counterparty risk that no institution warehouses at size.

THE FROZEN RULE (all five must hold; ANY miss = KILL):
  R1 YIELD      pooled net yield on DEPLOYED capital >= +8%/yr, maker fees, measured turnover.
  R2 BREADTH    >= 10 distinct symbols contribute at least one episode.
  R3 EPISODES   >= 5 distinct episodes contribute.
  R4 CONCENTRATION  the top-2 episodes are < 70% of total net PnL.
  R5 REGIME     net PnL positive in >= 2 disjoint calendar years.

ACCOUNTING (stated because it decides the verdict, and is the conservative choice):
  * Capital model is the CERTIFIED one (`CarryPortfolio`, src/coinmon/backtest/portfolio.py:171):
    with cash C the spot leg buys C/2 and the 1x perp short posts C/2 margin, so funding accrues on
    notional C/2 — only HALF the deployed capital earns. Entry pays maker on both legs (2 * C/2 *
    maker = C*maker), exit the same, so an episode costs 2*C*maker = 4bp round trip.
    A unified-margin book that uses spot as collateral would run notional ~= C and roughly DOUBLE
    the yield; that variant is reported as a sensitivity but R1 is judged on the 0.5x book, to stay
    consistent with the existing certificate rather than to flatter the probe.
  * "Yield on deployed capital" = total net PnL / (capital-time actually committed), annualized —
    i.e. return per unit of capital-year while the hedge is ON. Calendar yield (idle cash earning
    zero between episodes) is ALSO reported, because that is what a single-strategy account earns.
  * POINT-IN-TIME: the gate at print t uses prints t-2..t and the position collects from print t+1
    onward. No print is ever collected on the same bar its own rate informed the decision.
  * Funding interval is measured PER SYMBOL from the timestamps (48 bybit perps settle 8h, 10
    settle 4h) — assuming 8h everywhere would misannualize the 4h legs by 2x.

HONESTY CAVEATS (flagged before running, not after):
  * BASIS IS UNMODELLED. The certified model assumes the spot and perp price legs cancel exactly;
    we hold one candle series per coin, not a spot AND a perp series, so basis convergence PnL
    cannot be computed here. Direction of the bias: we ENTER when funding is hot (perp at a wide
    premium) and EXIT when it cools (premium compressed), and a long-spot/short-perp book GAINS on
    that compression — so the omission is more likely a tailwind than a hidden cost. The adverse
    case (basis widens further after entry, position closed into it) is real and unmeasured. This
    probe therefore cannot settle basis risk; a PASS licenses the next step, not deployment.
  * SURVIVORSHIP. The 58 funded symbols are today's surviving bybit perps; the DB holds 0
    delistings ([[b13-low-vol-fresh-lead]]). Carry is far less survivorship-sensitive than
    cross-sectional returns (funding is collected regardless of the coin's fate), but a delisted
    coin's final episode could have ended in a forced close this probe never sees.
  * C5 clustering is the expected cert risk: episodes will pile into the 2021 and 2024 manias.
    Two separate manias exist in-sample, which is why R5 asks for 2 disjoint years rather than more.

Run:
  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
  PYTHONPATH="src;." .venv/Scripts/python probes/f1_tail_gated_carry.py
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

import numpy as np
import pandas as pd

from coinmon.data import db

EXCHANGE = "bybit"
MAKER = 0.0002  # probe-standard maker fee (probes/b20_hourofday_window.py:42)
ENTER_ANN = 0.30  # arm the hedge when trailing-3 mean funding annualizes >= +30%
EXIT_ANN = 0.10  # disarm when it falls below +10% (hysteresis band, not a single threshold)
TRAIL = 3  # prints in the trailing mean, per the pre-registered spec
NOTIONAL = 0.5  # funding-earning notional per unit of deployed capital (self-funded 1x book)
MIN_PRINTS = 200  # a symbol needs a real history before its episodes mean anything
HOURS_PER_YEAR = 8760.0


@dataclass(frozen=True)
class Episode:
    """One armed period: capital committed from `start` to `end`, earning `gross` before fees."""

    symbol: str
    start: pd.Timestamp
    end: pd.Timestamp
    n_prints: int
    years_deployed: float
    gross: float  # funding collected per unit of deployed capital
    net: float  # ... after the round-trip maker fees


def funding_frame(conn, symbol: str) -> tuple[pd.DataFrame, float] | None:
    """Funding history as a `(time, rate, ann)` frame plus the symbol's settlement interval (hours).

    `ann` annualizes each print by the symbol's OWN measured cadence, so 4h and 8h perps are
    directly comparable. Returns None when the history is too short to gate on.
    """
    f = db.read_funding(conn, EXCHANGE, symbol)
    if len(f) < MIN_PRINTS:
        return None
    t = pd.to_datetime(f["funding_time"].to_numpy(), unit="ms", utc=True)
    rate = f["rate"].to_numpy(dtype=float)
    interval_h = float(np.median(np.diff(f["funding_time"].to_numpy())) / 3.6e6)
    if not 0.5 <= interval_h <= 24.0:  # a broken/gapped series, not a cadence we can annualize
        return None
    frame = pd.DataFrame({"rate": rate, "ann": rate * (HOURS_PER_YEAR / interval_h)}, index=t)
    return frame, interval_h


def armed_series(
    frame: pd.DataFrame, enter_ann: float = ENTER_ANN, exit_ann: float = EXIT_ANN
) -> np.ndarray:
    """The tradable armed mask: OFF -> ON when the trailing-`TRAIL` mean annualized funding is
    >= `enter_ann`, ON -> OFF when it drops below `exit_ann`.

    The decision made at print t governs collection from print t+1 (point-in-time), so the raw
    state is shifted by one before being returned.
    """
    trail = frame["ann"].rolling(TRAIL).mean()
    armed = np.zeros(len(frame), dtype=bool)
    on = False
    for i, m in enumerate(trail.to_numpy()):
        if np.isnan(m):
            continue
        on = m >= enter_ann if not on else m >= exit_ann
        armed[i] = on
    collect = np.roll(armed, 1)
    collect[0] = False
    return collect


def episodes(
    frame: pd.DataFrame, interval_h: float, symbol: str,
    enter_ann: float = ENTER_ANN, exit_ann: float = EXIT_ANN,
) -> list[Episode]:
    """Run the hysteresis gate and cut the armed prints into episodes."""
    collect = armed_series(frame, enter_ann, exit_ann)
    out: list[Episode] = []
    rates = frame["rate"].to_numpy()
    i = 0
    while i < len(collect):
        if not collect[i]:
            i += 1
            continue
        j = i
        while j < len(collect) and collect[j]:
            j += 1
        n = j - i
        gross = float(rates[i:j].sum()) * NOTIONAL
        out.append(
            Episode(
                symbol=symbol,
                start=frame.index[i],
                end=frame.index[j - 1],
                n_prints=n,
                years_deployed=n * interval_h / HOURS_PER_YEAR,
                gross=gross,
                net=gross - 2.0 * MAKER,  # one round trip per episode
            )
        )
        i = j
    return out


def always_on(frame: pd.DataFrame, interval_h: float) -> tuple[float, float]:
    """The ungated baseline: hold the hedge for the whole history. Returns (net PnL, years)."""
    gross = float(frame["rate"].sum()) * NOTIONAL
    return gross - 2.0 * MAKER, len(frame) * interval_h / HOURS_PER_YEAR


def main() -> None:
    conn = db.connect()
    symbols = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT symbol FROM funding_rates WHERE exchange = %s ORDER BY 1", (EXCHANGE,)
        ).fetchall()
    ]
    print("F1 tail-gated funding carry — arm at trailing-3 funding >= "
          f"{ENTER_ANN:.0%}/yr, disarm below {EXIT_ANN:.0%}/yr")
    print(f"   maker {MAKER:.2%}/leg, funding notional {NOTIONAL:g}x deployed capital, "
          f"{len(symbols)} funded {EXCHANGE} perps\n")

    all_eps: list[Episode] = []
    loaded_syms: dict[str, tuple[pd.DataFrame, float]] = {}
    base_pnl = base_years = 0.0
    span_lo, span_hi = None, None
    used = 0
    for sym in symbols:
        loaded = funding_frame(conn, sym)
        if loaded is None:
            continue
        frame, interval_h = loaded
        loaded_syms[sym] = (frame, interval_h)
        used += 1
        span_lo = frame.index[0] if span_lo is None else min(span_lo, frame.index[0])
        span_hi = frame.index[-1] if span_hi is None else max(span_hi, frame.index[-1])
        all_eps.extend(episodes(frame, interval_h, sym))
        p, y = always_on(frame, interval_h)
        base_pnl += p
        base_years += y
    conn.close()

    if not all_eps:
        print("no episodes — the gate never armed. KILL.")
        return

    total_net = sum(e.net for e in all_eps)
    total_gross = sum(e.gross for e in all_eps)
    total_years = sum(e.years_deployed for e in all_eps)
    calendar_years = (span_hi - span_lo).days / 365.25
    yield_deployed = total_net / total_years if total_years else 0.0
    # Calendar view: the same PnL spread over ONE account's wall-clock life (idle cash earns zero).
    # Episodes overlap across symbols, so this is the yield of a book that can hold all of them.
    yield_calendar = total_net / calendar_years if calendar_years else 0.0
    base_yield = base_pnl / base_years if base_years else 0.0

    by_symbol: dict[str, float] = {}
    for e in all_eps:
        by_symbol[e.symbol] = by_symbol.get(e.symbol, 0.0) + e.net
    by_year: dict[int, float] = {}
    year_deployed: dict[int, float] = {}
    for e in all_eps:
        y = int(e.start.year)
        by_year[y] = by_year.get(y, 0.0) + e.net
        year_deployed[y] = year_deployed.get(y, 0.0) + e.years_deployed

    ranked = sorted(all_eps, key=lambda e: e.net, reverse=True)
    top2 = sum(e.net for e in ranked[:2])
    top2_share = top2 / total_net if total_net > 0 else float("inf")

    print(f"COVERAGE  {used} symbols with >= {MIN_PRINTS} prints, "
          f"{span_lo.date()} -> {span_hi.date()} ({calendar_years:.1f} calendar years)")
    print(f"GATE      {len(all_eps)} episodes, {sum(e.n_prints for e in all_eps)} armed prints, "
          f"{total_years:.2f} capital-years deployed "
          f"({total_years / (used * calendar_years):.2%} of the universe's available time)\n")

    print("YIELD (per unit of DEPLOYED capital, annualized)")
    print(f"  gated   gross {total_gross / total_years:+7.2%}/yr   "
          f"net {yield_deployed:+7.2%}/yr   (fees {2 * MAKER * len(all_eps) / total_years:.2%}/yr)")
    print(f"  always-on baseline                net {base_yield:+7.2%}/yr   "
          f"({base_years:.0f} capital-years — this is the W3 book)")
    print(f"  gated, unified-margin 1x notional net {yield_deployed * 2:+7.2%}/yr   "
          f"(sensitivity only, NOT the judged number)")
    print(f"\n  all-symbols-at-once sum {yield_calendar:+.2%}/yr — NOT an account's yield: it gives "
          f"every symbol\n  its own full unit of capital. See D-A for the real one-account number.\n")

    print("TOP 10 EPISODES BY NET PnL (per unit of capital deployed in that episode)")
    hdr = f"{'symbol':>16}{'start':>12}{'end':>12}{'prints':>8}{'days':>7}{'net':>9}{'share':>8}"
    print(hdr)
    print("-" * len(hdr))
    for e in ranked[:10]:
        print(f"{e.symbol.split('/')[0]:>16}{str(e.start.date()):>12}{str(e.end.date()):>12}"
              f"{e.n_prints:>8}{e.years_deployed * 365:>7.1f}{e.net:>+9.2%}"
              f"{e.net / total_net if total_net else 0:>8.1%}")

    print("\nBY CALENDAR YEAR (episodes attributed to their START year)")
    hdr = f"{'year':>6}{'episodes':>10}{'cap-years':>11}{'net PnL':>10}{'yield/yr':>11}"
    print(hdr)
    print("-" * len(hdr))
    for y in sorted(by_year):
        n = sum(1 for e in all_eps if e.start.year == y)
        yd = year_deployed[y]
        print(f"{y:>6}{n:>10}{yd:>11.2f}{by_year[y]:>+10.2%}"
              f"{by_year[y] / yd if yd else 0:>+11.2%}")

    print(f"\nTOP 10 SYMBOLS BY NET PnL  (of {len(by_symbol)} contributing)")
    for s, v in sorted(by_symbol.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {s.split('/')[0]:>10}{v:>+10.2%}")

    # ---------------------------------------------------------------- the frozen verdict
    pos_years = sum(1 for y, v in by_year.items() if v > 0)
    r1 = yield_deployed >= 0.08
    r2 = len(by_symbol) >= 10
    r3 = len(all_eps) >= 5
    r4 = top2_share < 0.70
    r5 = pos_years >= 2
    ok = lambda b: "PASS" if b else "FAIL"
    print("\nFROZEN RULE")
    print(f"  R1 yield on deployed  {yield_deployed:+.2%}/yr  (need >= +8.00%)      [{ok(r1)}]")
    print(f"  R2 breadth            {len(by_symbol)} symbols (need >= 10)            [{ok(r2)}]")
    print(f"  R3 episodes           {len(all_eps)} episodes (need >= 5)              [{ok(r3)}]")
    print(f"  R4 concentration      top-2 = {top2_share:.1%} of PnL (need < 70%)  [{ok(r4)}]")
    print(f"  R5 regime             {pos_years}/{len(by_year)} years positive (need >= 2)     [{ok(r5)}]")
    passed = all((r1, r2, r3, r4, r5))
    print(f"\nF1 VERDICT: {'PASS' if passed else 'KILL'} — "
          f"tail-gated carry {'clears' if passed else 'does not clear'} the pre-registered bar. "
          f"Gated vs always-on: {yield_deployed:+.2%}/yr vs {base_yield:+.2%}/yr on deployed capital.")
    if passed:
        print("  NOTE: a PASS licenses the next step (basis modelling + live-paper), not deployment "
              "— basis PnL is unmodelled here (see docstring).")

    diagnostics(loaded_syms, span_lo, span_hi)


# ============================================================ POST-VERDICT DIAGNOSTICS (not frozen)
# Added AFTER the frozen rule was run and logged; these do not change the R1-R5 verdict above. They
# answer the three questions the frozen rule cannot: what does ONE account actually earn, is the
# edge still alive in the recent regime the deploy hurdle weights ([[live-yield-hurdle]]), and is
# "tail-gated" even the right word for a threshold this loose.

def portfolio_stream(
    loaded: dict[str, tuple[pd.DataFrame, float]], enter_ann: float, exit_ann: float
) -> pd.Series:
    """Daily net return of ONE equal-weight account that splits its capital across whatever is
    armed that day, and sits in cash (earning zero) when nothing is.

    Per symbol the daily stream is the funding collected on armed prints (on `NOTIONAL` of the
    capital allocated to that symbol) minus a maker fee at each episode's open and close. The
    account return is the mean across the symbols armed that day — so being armed on 1 coin and on
    30 coins both mean "fully invested", which is what an equal-weight book does.
    """
    pnl_cols, armed_cols = {}, {}
    for sym, (frame, _iv) in loaded.items():
        collect = armed_series(frame, enter_ann, exit_ann)
        if not collect.any():
            continue
        flow = np.where(collect, frame["rate"].to_numpy() * NOTIONAL, 0.0)
        edges = np.diff(np.concatenate(([False], collect, [False])).astype(int))
        # edges[i] = p[i+1]-p[i] on the zero-padded mask: edges[:-1]==1 marks each episode's first
        # armed print, edges[1:]==-1 marks its last.
        flow[edges[:-1] == 1] -= MAKER  # episode open
        flow[edges[1:] == -1] -= MAKER  # episode close
        s = pd.Series(flow, index=frame.index)
        a = pd.Series(collect, index=frame.index)
        pnl_cols[sym] = s.resample("1D").sum()
        armed_cols[sym] = a.resample("1D").max().fillna(False).astype(bool)
    pnl = pd.DataFrame(pnl_cols).fillna(0.0)
    armed = pd.DataFrame(armed_cols).reindex_like(pnl).fillna(False).astype(bool)
    n_armed = armed.sum(axis=1)
    return (pnl.where(armed, 0.0).sum(axis=1) / n_armed.replace(0, np.nan)).fillna(0.0)


def diagnostics(
    loaded: dict[str, tuple[pd.DataFrame, float]], span_lo: pd.Timestamp, span_hi: pd.Timestamp
) -> None:
    print("\n" + "=" * 78)
    print("POST-VERDICT DIAGNOSTICS — not part of the frozen rule, do not change the verdict")
    print("=" * 78)

    # ---- D-A: what ONE account earns
    daily = portfolio_stream(loaded, ENTER_ANN, EXIT_ANN)
    invested = (daily != 0).mean()
    print("\nD-A  ONE-ACCOUNT EQUAL-WEIGHT BOOK (capital split across whatever is armed; cash else)")
    print(f"     calendar yield {daily.mean() * 365:+.2%}/yr over {len(daily) / 365.25:.1f} years, "
          f"invested on {invested:.1%} of days")
    print("     by year:")
    for y, g in daily.groupby(daily.index.year):
        act = float((g != 0).mean())
        print(f"       {y}  {g.mean() * 365:+7.2%}/yr   invested {act:>5.1%} of days")

    # ---- D-B: the recent regime the deploy hurdle weights
    cutoff = span_hi - pd.Timedelta(days=730)
    recent = daily[daily.index >= cutoff]
    rec_eps, rec_years, rec_net = 0, 0.0, 0.0
    for sym, (frame, iv) in loaded.items():
        for e in episodes(frame, iv, sym):
            if e.end >= cutoff:
                rec_eps += 1
                rec_years += e.years_deployed
                rec_net += e.net
    print(f"\nD-B  RECENT REGIME (last 24 months, {cutoff.date()} -> {span_hi.date()})")
    print(f"     {rec_eps} episodes, {rec_years:.2f} capital-years deployed, "
          f"net {rec_net:+.2%} -> {rec_net / rec_years if rec_years else 0:+.2%}/yr on deployed")
    print(f"     one-account calendar yield {recent.mean() * 365:+.2%}/yr, "
          f"invested {(recent != 0).mean():.1%} of days")
    print("     ^ THIS is the number the >=5%/yr live hurdle judges, not the full-sample +18.89%.")

    # ---- D-C: is the gate actually selecting a TAIL?
    print("\nD-C  GATE-THRESHOLD SENSITIVITY (bybit baseline funding is 0.01%/8h = ~11%/yr, so a")
    print("     30%/yr arm is only ~2.7x baseline — looser than the word 'tail' implies)")
    hdr = f"{'arm at':>9}{'episodes':>10}{'cap-yrs':>9}{'net/yr':>10}{'1-acct/yr':>11}{'days in':>9}"
    print(hdr)
    print("-" * len(hdr))
    for enter in (0.30, 0.60, 1.00, 2.00):
        eps = [e for sym, (fr, iv) in loaded.items()
               for e in episodes(fr, iv, sym, enter_ann=enter, exit_ann=enter / 3.0)]
        if not eps:
            print(f"{enter:>8.0%}   (never arms)")
            continue
        yrs = sum(e.years_deployed for e in eps)
        net = sum(e.net for e in eps)
        d = portfolio_stream(loaded, enter, enter / 3.0)
        print(f"{enter:>8.0%}{len(eps):>10}{yrs:>9.2f}{net / yrs:>+10.2%}"
              f"{d.mean() * 365:>+11.2%}{(d != 0).mean():>9.1%}")


if __name__ == "__main__":
    main()
