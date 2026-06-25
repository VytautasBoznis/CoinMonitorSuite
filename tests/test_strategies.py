from coinmon.data.models import Candle
from coinmon.feed import BarView, CostModel
from coinmon.strategies.ema_crossover import EMACrossover
from coinmon.strategies.rsi_meanreversion import RSIMeanReversion

ZERO_COST = CostModel(taker_fee=0.0)


def _views(closes, features_seq=None):
    out = []
    for i, c in enumerate(closes):
        feats = features_seq[i] if features_seq is not None else {}
        candle = Candle(open_time=i, open=c, high=c, low=c, close=c, volume=1.0)
        out.append(BarView(candle=candle, features=feats))
    return out


def _run(strategy, views):
    return [strategy.on_bar(v) for v in views]


def test_ema_goes_long_on_uptrend_and_flat_on_downtrend():
    closes = [10.0] * 5 + [float(p) for p in range(11, 40)] + [float(p) for p in range(39, 10, -1)]
    targets = _run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes))
    assert 1 in targets  # entered long during the rally
    assert targets[-1] == 0  # exited flat by the end of the decline


def test_ema_cost_band_suppresses_churn():
    # Tiny oscillations around a flat level: the EMA spread never clears the round-trip
    # cost, so a banded strategy must stay flat the whole way.
    closes = [100.0 + (0.05 if i % 2 else -0.05) for i in range(60)]
    views = _views(closes)
    banded = EMACrossover(CostModel(taker_fee=0.001), fast=3, slow=8)  # band = 0.002 (20 bps)
    assert set(_run(banded, views)) == {0}
    # With zero cost the same wiggles do flip the target at least once (band is what helps).
    assert set(_run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes))) != {0}


def test_rsi_enters_oversold_exits_on_recovery():
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    targets = _run(RSIMeanReversion(period=5, oversold=30.0, exit_level=50.0), _views(closes))
    assert 1 in targets  # bought the dip
    assert targets[-1] == 0  # released after recovery


def test_no_lookahead_a_target_depends_only_on_past():
    # The decision at bar t must be identical whether or not future bars exist: running a
    # fresh strategy on the prefix [0..t] reproduces the full-run target at t.
    closes = [float(p) for p in range(40, 20, -1)] + [float(p) for p in range(21, 45)]
    full = _run(RSIMeanReversion(period=5), _views(closes))
    for t in (10, 20, 30, len(closes) - 1):
        prefix = _run(RSIMeanReversion(period=5), _views(closes[: t + 1]))
        assert prefix[-1] == full[t]


def test_precomputed_features_bypass_internal_compute():
    # A feed that supplies ema features drives the same decision as internal computation;
    # here the features are crafted so fast leads slow -> long.
    closes = [100.0, 100.0, 100.0]
    feats = [
        {"ema_3": 100.0, "ema_8": 100.0},
        {"ema_3": 105.0, "ema_8": 100.0},
        {"ema_3": 110.0, "ema_8": 100.0},
    ]
    targets = _run(EMACrossover(ZERO_COST, fast=3, slow=8), _views(closes, feats))
    assert targets[-1] == 1
