import math

import pandas as pd
import pytest

from coinmon.backtest.engine import BacktestEngine, BarStepper
from coinmon.backtest.metrics import summarize
from coinmon.backtest.portfolio import PerpPortfolio, SpotPortfolio
from coinmon.data.candles import load_candles
from coinmon.data.models import Candle
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy
from coinmon.strategies.directional import ShortWhenFlat


class _AlwaysLong(Strategy):
    def on_bar(self, view: BarView) -> int:
        return 1


class _Scripted(Strategy):
    """Replays a fixed list of targets, one per bar."""

    def __init__(self, targets):
        self._targets = list(targets)
        self._i = -1

    def on_bar(self, view: BarView) -> int:
        self._i += 1
        return self._targets[self._i]


def _candles(rows):
    # rows: list of (open, close); high/low bound them, volume constant.
    return pd.DataFrame(
        {
            "open_time": range(len(rows)),
            "open": [o for o, _ in rows],
            "high": [max(o, c) for o, c in rows],
            "low": [min(o, c) for o, c in rows],
            "close": [c for _, c in rows],
            "volume": [1.0] * len(rows),
        }
    )


def test_spot_portfolio_round_trip_pays_two_taker_fees():
    p = SpotPortfolio(cash=100.0, taker_fee=0.01)
    p.rebalance(1, price=10.0)  # buy: 100 * 0.99 / 10 = 9.9 units
    assert p.units == pytest.approx(9.9)
    assert p.equity(10.0) == pytest.approx(99.0)
    p.rebalance(0, price=10.0)  # sell: 9.9 * 10 * 0.99 = 98.01
    assert p.units == 0.0
    assert p.equity(10.0) == pytest.approx(98.01)  # ~2% lost to two 1% fees


def test_rebalance_to_same_target_is_a_noop():
    p = SpotPortfolio(cash=100.0, taker_fee=0.5)
    p.rebalance(1, price=10.0)
    units = p.units
    p.rebalance(1, price=999.0)  # no second fee, no re-trade
    assert p.units == units


def test_closed_round_trip_records_realized_pnl():
    p = SpotPortfolio(cash=100.0, taker_fee=0.0)
    p.rebalance(1, price=10.0)  # buy 10 units
    p.rebalance(0, price=12.0)  # sell at 12 -> 120 cash
    assert p.trades == [pytest.approx(20.0)]  # +20 realized on the round-trip


def test_open_position_is_not_a_closed_trade():
    p = SpotPortfolio(cash=100.0, taker_fee=0.0)
    p.rebalance(1, price=10.0)  # entered, never exited
    assert p.trades == []  # unrealized, so no trade recorded


class _AlwaysFlat(Strategy):
    def on_bar(self, view: BarView) -> int:
        return 0


def test_perp_leverage_one_round_trip_pays_two_notional_fees():
    # A 1x perp long ~ a spot long, but the taker fee is on the full notional each leg (the
    # margin is held separately from the position), so a round trip costs 2 x fee x notional.
    p = PerpPortfolio(cash=100.0, taker_fee=0.01, leverage=1.0)
    p.rebalance(1, price=10.0)
    assert p.equity(10.0) == pytest.approx(99.0)  # paid the 1% entry fee on 100 notional
    p.rebalance(0, price=10.0)
    assert p.equity(10.0) == pytest.approx(98.0)  # two 1% notional fees


def test_perp_short_profits_when_price_falls():
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=1.0)
    p.rebalance(-1, price=10.0)  # open short
    assert p.units == pytest.approx(-10.0)
    assert p.equity(8.0) == pytest.approx(120.0)  # 20% drop -> +20 on a 1x short
    p.rebalance(0, price=8.0)  # close
    assert p.trades == [pytest.approx(20.0)]


def test_perp_leverage_scales_pnl():
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=3.0)
    p.rebalance(-1, price=10.0)
    assert p.equity(9.0) == pytest.approx(130.0)  # 10% drop x3 leverage -> +30%


def test_perp_over_leveraged_adverse_move_liquidates():
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=3.0)
    p.rebalance(-1, price=10.0)  # 3x short: ~33% rally wipes the collateral
    assert p.equity(14.0) == pytest.approx(0.0)  # liquidated, equity floored at 0
    assert p.trades == [pytest.approx(-100.0)]  # whole collateral booked as the loss
    # The account is dead: no further trade, and a price recovery does NOT un-liquidate it.
    p.rebalance(-1, price=10.0)
    assert p.equity(8.0) == pytest.approx(0.0)


def test_perp_flip_long_to_short_closes_then_reopens():
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=1.0)
    p.rebalance(1, price=10.0)  # long
    p.rebalance(-1, price=12.0)  # flip: realize +20 on the long, open a short at 12
    assert p.trades == [pytest.approx(20.0)]  # the closed long round-trip
    assert p.units == pytest.approx(-10.0)  # now short 120-notional / 12


def test_engine_short_position_marks_and_counts_exposure():
    # Always short on a falling market: held a short on bars 1-3, so exposure = 3/4 and the mark
    # rises as price drops.
    candles = _candles([(100.0, 100.0), (100.0, 90.0), (90.0, 80.0), (80.0, 70.0)])
    result = BacktestEngine(_Scripted([-1, -1, -1, -1]), PerpPortfolio(100.0, 0.0)).run(candles)
    assert result.equity_curve.iloc[-1] == pytest.approx(130.0)  # +30 from a 30-point drop
    assert result.metrics["exposure"] == pytest.approx(0.75)


def test_short_when_flat_beats_spot_long_in_a_downtrend():
    # The capability proof: same falling series, long/flat spot bleeds while ShortWhenFlat on a
    # perp turns the flat signal into a short and profits from the drop.
    candles = _candles([(100.0, 100.0), (100.0, 90.0), (90.0, 80.0), (80.0, 70.0)])
    long_spot = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(candles)
    short_perp = BacktestEngine(
        ShortWhenFlat(_AlwaysFlat()), PerpPortfolio(100.0, 0.0)
    ).run(candles)
    assert long_spot.equity_curve.iloc[-1] < 100.0 < short_perp.equity_curve.iloc[-1]


def test_engine_executes_at_next_bar_open_not_signal_bar_close():
    # Signal fires after bar 0 closes; it must fill at bar 1's OPEN (10), so the close-of-bar-0
    # jump to 20 is NOT captured — only the move from the next open onward is.
    candles = _candles([(10.0, 20.0), (10.0, 30.0)])
    portfolio = SpotPortfolio(cash=100.0, taker_fee=0.0)
    result = BacktestEngine(_AlwaysLong(), portfolio).run(candles)
    # Bought 10 units at open=10 on bar 1, marked at close=30 -> 300.
    assert result.equity_curve.iloc[0] == pytest.approx(100.0)  # bar 0: still flat
    assert result.equity_curve.iloc[-1] == pytest.approx(300.0)


def test_final_bar_signal_never_trades():
    # Flat the whole way, then a long signal on the very last bar: no bar t+1 exists to fill
    # it, so equity stays at the starting cash throughout.
    candles = _candles([(10.0, 10.0), (10.0, 10.0), (10.0, 50.0)])
    portfolio = SpotPortfolio(cash=100.0, taker_fee=0.0)
    result = BacktestEngine(_Scripted([0, 0, 1]), portfolio).run(candles)
    assert list(result.equity_curve) == pytest.approx([100.0, 100.0, 100.0])


def test_engine_rejects_empty_frame():
    with pytest.raises(ValueError):
        BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(_candles([]))


def test_engine_reports_trade_count_and_exposure():
    # Enter long (fills at bar 1's open=10), exit (fills at bar 2's open=15) -> one winning
    # round-trip. Held a position only during bar 1, so exposure = 1/4.
    candles = _candles([(10.0, 10.0), (10.0, 10.0), (15.0, 15.0), (15.0, 15.0)])
    result = BacktestEngine(_Scripted([1, 0, 0, 0]), SpotPortfolio(100.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 1
    assert result.metrics["win_rate"] == pytest.approx(1.0)
    assert result.metrics["exposure"] == pytest.approx(0.25)


def test_buy_and_hold_has_no_closed_trades():
    # Always long never completes a round-trip: 0 trades, n/a win rate, ~full exposure.
    candles = _candles([(10.0, 10.0), (10.0, 20.0), (20.0, 30.0)])
    result = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(candles)
    assert result.metrics["trades"] == 0
    assert math.isnan(result.metrics["win_rate"])
    assert math.isnan(result.metrics["profit_factor"])
    assert "n/a" in result.summary()  # rendered, not crashed


def test_metrics_curve_fields():
    curve = pd.Series([100.0, 120.0, 90.0, 108.0])
    m = summarize(curve, trades=[], exposure=0.5)
    assert m["total_return"] == pytest.approx(0.08)
    assert m["max_drawdown"] == pytest.approx(90.0 / 120.0 - 1.0)  # -0.25
    assert m["exposure"] == pytest.approx(0.5)


def test_metrics_per_trade_win_rate_and_profit_factor():
    m = summarize(pd.Series([100.0, 110.0]), trades=[30.0, -10.0, 20.0], exposure=1.0)
    assert m["trades"] == 3
    assert m["win_rate"] == pytest.approx(2 / 3)
    assert m["profit_factor"] == pytest.approx(50.0 / 10.0)  # gross 50 won / 10 lost


def _ohlc(rows):
    # rows: list of (open, high, low, close) — full control of the bar for intrabar-stop tests.
    return pd.DataFrame(
        {
            "open_time": range(len(rows)),
            "open": [o for o, _, _, _ in rows],
            "high": [h for _, h, _, _ in rows],
            "low": [low for _, _, low, _ in rows],
            "close": [c for _, _, _, c in rows],
            "volume": [1.0] * len(rows),
        }
    )


def test_no_stop_leaves_engine_byte_unchanged():
    # Parity: stop_pct=None must reproduce the no-stop engine exactly (the default path).
    candles = _candles([(10.0, 10.0), (10.0, 12.0), (12.0, 8.0), (8.0, 9.0)])
    base = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.001)).run(candles)
    stopless = BacktestEngine(
        _AlwaysLong(), SpotPortfolio(100.0, 0.001), stop_pct=None
    ).run(candles)
    assert list(stopless.equity_curve) == pytest.approx(list(base.equity_curve))


def test_intrabar_stop_caps_a_long_loss_at_the_stop_level():
    # Long fills at bar 1's open (10); the bar then dips to a low of 8, through the 10% stop at 9.
    # With the stop the position exits at 9 (cash 90); without it the long rides the close to 8.5.
    candles = _ohlc([(10.0, 10.0, 10.0, 10.0), (10.0, 10.0, 8.0, 8.5)])
    stopped = BacktestEngine(
        _AlwaysLong(), SpotPortfolio(100.0, 0.0), stop_pct=0.10
    ).run(candles)
    unstopped = BacktestEngine(_AlwaysLong(), SpotPortfolio(100.0, 0.0)).run(candles)
    assert stopped.equity_curve.iloc[-1] == pytest.approx(90.0)  # exited at the 9.0 stop level
    assert unstopped.equity_curve.iloc[-1] == pytest.approx(85.0)  # rode the bar down to 8.5


def test_intrabar_stop_prevents_a_leveraged_short_liquidation():
    # 3x short fills at bar 1's open (10); the bar rallies to a high of 14. Unstopped, the +40%
    # mark wipes the 3x collateral (liquidation, equity 0); a 10% stop exits at 11 (a -30% loss)
    # and survives — exactly the brake chunk L needs so leverage isn't synonymous with ruin.
    candles = _ohlc(
        [(10.0, 10.0, 10.0, 10.0), (10.0, 14.0, 10.0, 14.0), (14.0, 14.0, 14.0, 14.0)]
    )
    stopped = BacktestEngine(
        ShortWhenFlat(_AlwaysFlat()), PerpPortfolio(100.0, 0.0, 3.0), stop_pct=0.10
    ).run(candles)
    liquidated = BacktestEngine(
        ShortWhenFlat(_AlwaysFlat()), PerpPortfolio(100.0, 0.0, 3.0)
    ).run(candles)
    assert stopped.equity_curve.iloc[-1] == pytest.approx(70.0)  # exited the short at 11
    assert liquidated.equity_curve.iloc[-1] == pytest.approx(0.0)  # collateral wiped


def test_stop_suppresses_reentry_until_the_signal_resets():
    # A stop-out latches flat: the strategy keeps shouting "long" (suppressed) until its signal
    # leaves the stopped side (goes flat), after which a fresh long is allowed to re-arm and fill.
    stepper = BarStepper(_Scripted([1, 1, 1, 0, 1, 1]), SpotPortfolio(100.0, 0.0), stop_pct=0.10)
    rows = [
        (10.0, 10.0, 10.0, 10.0),  # bar 0: decide long
        (10.0, 10.0, 8.0, 9.0),  # bar 1: fill long @10, stopped @9 -> flat, latch
        (9.0, 9.0, 9.0, 9.0),  # bar 2: signal still long -> suppressed, stay flat
        (9.0, 9.0, 9.0, 9.0),  # bar 3: signal resets to flat -> latch cleared
        (9.0, 9.0, 9.0, 9.0),  # bar 4: signal long again -> re-arm pending
        (11.0, 11.0, 11.0, 11.0),  # bar 5: fill the fresh long @11
    ]
    candles = [
        Candle(open_time=i, open=o, high=h, low=low, close=c, volume=1.0)
        for i, (o, h, low, c) in enumerate(rows)
    ]
    positions = [stepper.step(c).position for c in candles]
    assert positions == [0, 0, 0, 0, 0, 1]


# --- Chunk W3: perp funding cashflow -----------------------------------------------------------


def test_perp_funding_long_pays_short_receives():
    # rate > 0 => longs pay shorts. Charge = units * price * rate = 10 * 10 * 0.01 = 1.0.
    long = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=1.0)
    long.rebalance(1, price=10.0)  # units = +10
    long.apply_funding(rate=0.01, price=10.0)
    assert long.equity(10.0) == pytest.approx(99.0)  # long bled the funding
    short = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=1.0)
    short.rebalance(-1, price=10.0)  # units = -10
    short.apply_funding(rate=0.01, price=10.0)
    assert short.equity(10.0) == pytest.approx(101.0)  # short collected the funding


def test_perp_funding_is_a_noop_when_flat_or_liquidated():
    flat = PerpPortfolio(cash=100.0, taker_fee=0.0)
    flat.apply_funding(rate=0.5, price=10.0)  # no open position -> no cashflow
    assert flat.equity(10.0) == pytest.approx(100.0)
    dead = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=3.0)
    dead.rebalance(-1, price=10.0)
    dead.equity(14.0)  # ~40% rally wipes the 3x collateral -> liquidated
    dead.apply_funding(rate=-0.5, price=14.0)  # funding must not resurrect the dead account
    assert dead.equity(14.0) == pytest.approx(0.0)


def test_spot_funding_is_a_noop():
    p = SpotPortfolio(cash=100.0, taker_fee=0.0)
    p.rebalance(1, price=10.0)
    p.apply_funding(rate=0.5, price=10.0)  # spot pays no funding
    assert p.equity(10.0) == pytest.approx(100.0)


def test_perp_funding_flows_into_the_round_trip_pnl():
    # Open and close at the same price: the only PnL is the funding paid while held.
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=1.0)
    p.rebalance(1, price=10.0)
    p.apply_funding(rate=0.01, price=10.0)  # pays 1.0
    p.rebalance(0, price=10.0)
    assert p.trades == [pytest.approx(-1.0)]  # the round-trip lost exactly the funding paid


def test_perp_funding_can_trigger_liquidation():
    # A short bleeding to negative funding: enough charges push collateral below zero -> liq.
    p = PerpPortfolio(cash=100.0, taker_fee=0.0, leverage=3.0)
    p.rebalance(-1, price=10.0)  # units = -30
    p.apply_funding(rate=-0.2, price=10.0)  # short pays: cash 100 -> 40
    assert p.equity(10.0) == pytest.approx(40.0)
    p.apply_funding(rate=-0.2, price=10.0)  # cash 40 -> -20
    assert p.equity(10.0) == pytest.approx(0.0)  # collateral gone -> liquidated
    assert p.trades == [pytest.approx(-100.0)]


def test_engine_zero_funding_matches_no_funding():
    # Parity: an all-zero funding series charges nothing and must reproduce the no-funding run.
    candles = _candles([(10.0, 10.0), (10.0, 12.0), (12.0, 8.0), (8.0, 9.0)])
    base = BacktestEngine(_AlwaysLong(), PerpPortfolio(100.0, 0.0)).run(candles)
    zero = BacktestEngine(_AlwaysLong(), PerpPortfolio(100.0, 0.0)).run(candles, funding=[0.0] * 4)
    assert list(zero.equity_curve) == pytest.approx(list(base.equity_curve))


def test_engine_funding_bleeds_a_held_perp_long():
    # Flat price, constant +1% funding: a 1x long held on bars 1-3 pays 10*10*0.01 = 1.0 each.
    candles = _candles([(10.0, 10.0)] * 4)
    engine = BacktestEngine(_AlwaysLong(), PerpPortfolio(100.0, 0.0))
    result = engine.run(candles, funding=[0.01] * 4)
    assert result.equity_curve.iloc[-1] == pytest.approx(97.0)  # 100 - 3 funding charges


def test_engine_exposes_funding_rate_as_a_feature():
    rates = [0.001, -0.002, 0.003, 0.0]

    class _FundingSpy(Strategy):
        def __init__(self):
            self.seen: list[float | None] = []

        def on_bar(self, view: BarView) -> int:
            self.seen.append(view.feature("funding_rate"))
            return 0

    spy = _FundingSpy()
    candles = _candles([(10.0, 10.0)] * 4)
    BacktestEngine(spy, SpotPortfolio(100.0, 0.0)).run(candles, funding=rates)
    assert spy.seen == pytest.approx(rates)  # point-in-time, one per bar, in order


def test_engine_funding_length_mismatch_raises():
    candles = _candles([(10.0, 10.0)] * 4)
    with pytest.raises(ValueError, match="align"):
        BacktestEngine(_AlwaysLong(), PerpPortfolio(100.0, 0.0)).run(candles, funding=[0.01] * 3)


def test_load_candles_usdc_pair_reads_directly():
    seen = []

    def read(symbol):
        seen.append(symbol)
        return _candles([(10.0, 11.0)])

    load_candles(read, "BTC/USDC")
    assert seen == ["BTC/USDC"]  # one direct read, no ratio synthesis


def test_load_candles_synthetic_ratio_reads_both_usdc_legs():
    legs = {
        "ETH/USDC": _candles([(200.0, 220.0)]),
        "BTC/USDC": _candles([(100.0, 110.0)]),
    }
    seen = []

    def read(symbol):
        seen.append(symbol)
        return legs[symbol]

    out = load_candles(read, "ETH/BTC")
    assert seen == ["ETH/USDC", "BTC/USDC"]  # both legs loaded vs USDC
    assert out["close"].iloc[0] == pytest.approx(110.0 / 110.0 * 2.0)  # 220/110 = 2.0
