import pandas as pd
import pytest

from coinmon.backtest.result import TradeRecord
from coinmon.search.evidence import (
    CertifiedRow,
    block_bootstrap_ci,
    build_carry_evidence,
    build_evidence,
    certify,
    certify_carry,
    pool_carry_bars,
    pool_segments,
    pool_trades,
    rank_certified,
    summarize_certified_sweep,
    wilson_lower_bound,
)
from coinmon.search.genome import Genome


def _ledger(returns, *, span=1000):
    """Synthetic trade ledger: each return at an entry time spread evenly over ``span`` so the
    regime buckets split it in half."""
    n = len(returns)
    return [
        TradeRecord(entry_time=int(i * span / n), exit_time=int(i * span / n) + 1,
                    direction=1, net_return_pct=r)
        for i, r in enumerate(returns)
    ]


def _win_loss(n, win_rate, win=0.02, loss=-0.01):
    """N returns interleaved so wins/losses alternate (win_rate fraction are wins)."""
    wins = round(n * win_rate)
    out = []
    for i in range(n):
        out.append(win if (i * wins) % n < wins else loss)
    # exact count fix
    got = sum(1 for r in out if r > 0)
    i = 0
    while got < wins and i < n:
        if out[i] < 0:
            out[i] = win
            got += 1
        i += 1
    return out


# --- Wilson bound (C2) ---

def test_wilson_lower_bound_known_value():
    # 165/300 = 55% observed -> one-sided 95% Wilson lower bound just above 0.50.
    assert wilson_lower_bound(165, 300) == pytest.approx(0.5025, abs=1e-3)


def test_wilson_lower_bound_at_fifty_percent_is_below_half():
    assert wilson_lower_bound(150, 300) < 0.50


def test_wilson_lower_bound_empty_is_zero():
    assert wilson_lower_bound(0, 0) == 0.0


# --- block bootstrap (C3) ---

def test_block_bootstrap_constant_returns_has_no_dispersion():
    lo, hi, std = block_bootstrap_ci([0.01] * 50, seed=0, resamples=500)
    assert lo == pytest.approx(0.01)
    assert hi == pytest.approx(0.01)
    assert std == pytest.approx(0.0)


def test_block_bootstrap_ci_brackets_the_mean():
    returns = _win_loss(300, 0.55)
    lo, hi, std = block_bootstrap_ci(returns, seed=1, resamples=2000)
    mean = sum(returns) / len(returns)
    assert lo < mean < hi
    assert std > 0


# --- certificate verdicts ---

def test_strong_ledger_certifies_at_n300():
    evidence = build_evidence(_ledger(_win_loss(300, 0.55)), seed=0, resamples=2000)
    cert = certify(evidence, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "CERTIFIED"


def test_pending_null_blocks_certification():
    evidence = build_evidence(_ledger(_win_loss(300, 0.55)), seed=0, resamples=2000)
    cert = certify(evidence)  # no null / fragility supplied
    assert cert.verdict == "UNPROVEN"
    assert any(status == "PENDING" for _, status, _ in cert.criteria)


def test_fifty_percent_ledger_is_refuted_at_n300():
    evidence = build_evidence(_ledger(_win_loss(300, 0.50)), seed=0, resamples=2000)
    cert = certify(evidence, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "REFUTED"


def test_small_sample_is_unproven():
    evidence = build_evidence(_ledger(_win_loss(20, 0.60)), seed=0, resamples=500)
    cert = certify(evidence, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "UNPROVEN"


def test_single_regime_fails_regime_spread():
    # all trades at the same instant -> one regime -> C5 fails even with N and win rate fine.
    trades = [
        TradeRecord(entry_time=0, exit_time=1, direction=1, net_return_pct=r)
        for r in _win_loss(300, 0.55)
    ]
    evidence = build_evidence(trades, seed=0, resamples=1000)
    cert = certify(evidence, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "REFUTED"
    assert next(s for c, s, _ in cert.criteria if c.startswith("C5")) == "FAIL"


def test_fragility_failure_refutes():
    evidence = build_evidence(_ledger(_win_loss(300, 0.55)), seed=0, resamples=1000)
    cert = certify(evidence, null_beaten=True, fragility_positive=0.5)
    assert cert.verdict == "REFUTED"


# --- chunk U.3: sweep certificate ranking ---

def _certified_row(pair, win_rate):
    evidence = build_evidence(_ledger(_win_loss(300, win_rate)), seed=0, resamples=500)
    genome = Genome(family="rsi_meanreversion", pair=pair, params={})
    return CertifiedRow(genome=genome, certificate=certify(evidence))


def test_rank_certified_orders_by_t_exp_best_first():
    weak = _certified_row("BTC/USDC", 0.51)
    strong = _certified_row("ETH/USDC", 0.60)
    ranked = rank_certified([weak, strong])
    assert [r.genome.pair for r in ranked] == ["ETH/USDC", "BTC/USDC"]
    assert ranked[0].certificate.evidence.t_exp >= ranked[1].certificate.evidence.t_exp


def test_summarize_certified_sweep_lists_and_tallies():
    rows = [_certified_row("BTC/USDC", 0.51), _certified_row("ETH/USDC", 0.60)]
    text = summarize_certified_sweep(rows)
    # both winners listed, and the verdict tally counts all of them
    assert "BTC/USDC" in text and "ETH/USDC" in text
    verdicts = [r.certificate.verdict for r in rows]
    assert f"{verdicts.count('REFUTED')} REFUTED of 2 GO winner(s)" in text


def test_summarize_certified_sweep_empty():
    assert summarize_certified_sweep([]) == "certified sweep — no GO winners to certify."


# --- pooling leakage guard ---

def test_pool_trades_only_evaluates_holdout_bars():
    # one window over the whole series, holdout = last half -> no pooled trade may enter before it.
    n = 120
    # an oscillating series so an rsi(2) mean-reversion genome actually trades.
    closes = [100 + (8 if i % 2 else -8) for i in range(n)]
    frame = pd.DataFrame(
        {
            "open_time": range(n),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        }
    )
    genome = Genome(
        family="rsi_meanreversion",
        pair="AAA/USDC",
        params={"period": 2, "oversold": 40.0, "exit_level": 60.0},
    )
    holdout_start = int(n * 0.5)  # window_size 1.0, holdout 0.5 -> tail starts at bar 60
    pooled = pool_trades(
        genome, lambda s: frame, 0.0, [genome.pair],
        window_size=1.0, step=1.0, holdout_fraction=0.5,
    )
    assert pooled, "expected the genome to trade in the holdout"
    assert min(t.entry_time for t in pooled) >= holdout_start


def test_pool_segments_matches_pool_trades_and_records_durations():
    # pool_segments must see the SAME OOS grid as pool_trades (they share _iter_segments): the total
    # trade count agrees, and every recorded (direction, duration) is a valid bar-index gap >= 1.
    n = 120
    closes = [100 + (8 if i % 2 else -8) for i in range(n)]
    frame = pd.DataFrame(
        {
            "open_time": range(n),
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1.0] * n,
        }
    )
    genome = Genome(
        family="rsi_meanreversion",
        pair="AAA/USDC",
        params={"period": 2, "oversold": 40.0, "exit_level": 60.0},
    )
    kwargs = dict(window_size=1.0, step=1.0, holdout_fraction=0.5)
    pooled = pool_trades(genome, lambda s: frame, 0.0, [genome.pair], **kwargs)
    segments = pool_segments(genome, lambda s: frame, 0.0, [genome.pair], **kwargs)
    assert segments
    assert sum(len(seg.trades) for seg in segments) == len(pooled)
    for seg in segments:
        assert len(seg.opens) == len(seg.closes)
        for direction, duration in seg.trades:
            assert direction in (-1, 1)
            assert 1 <= duration < len(seg.opens)


# --- W3 step 3b: the carry-appropriate (per-bar) certificate ---

def _carry_bars(returns, *, span=1000):
    """Synthetic per-bar carry ledger: each return at a time spread evenly over ``span`` so the
    regime buckets split it in half (mirrors ``_ledger`` for the per-trade certificate)."""
    n = len(returns)
    return [(int(i * span / n), r) for i, r in enumerate(returns)]


def _carry_ev(bars, n_pairs=5, *, resamples=500):
    return build_carry_evidence(bars, n_pairs, bars_per_year=365, seed=0, resamples=resamples)


def test_carry_positive_premium_passes_hard_criteria_pending_null():
    ev = _carry_ev(_carry_bars([0.001] * 400))
    cert = certify_carry(ev)  # null + fragility not supplied -> PENDING
    assert ev.mean_return > 0
    status = {c.split()[0]: s for c, s, _ in cert.criteria}
    assert status["C1"] == "PASS" and status["C3"] == "PASS" and status["C5"] == "PASS"
    assert cert.verdict == "UNPROVEN"  # hard criteria clean, but C4/C6 pending block CERTIFIED


def test_carry_certified_when_null_and_fragility_supplied():
    ev = _carry_ev(_carry_bars([0.001] * 400))
    cert = certify_carry(ev, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "CERTIFIED"


def test_carry_negative_premium_refuted():
    ev = _carry_ev(_carry_bars([-0.001] * 400))
    cert = certify_carry(ev, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "REFUTED"  # N over floor, mean/CI <= 0 -> C3 FAIL


def test_carry_small_sample_unproven():
    ev = _carry_ev(_carry_bars([0.001] * 50))
    cert = certify_carry(ev, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "UNPROVEN"  # below the 300-bar evidence floor


def test_carry_too_few_pairs_unproven():
    ev = _carry_ev(_carry_bars([0.001] * 400), n_pairs=1)
    cert = certify_carry(ev, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "UNPROVEN"  # C1 breadth: only 1 funded perp (< min_pairs 3)


def test_carry_single_regime_refuted():
    bars = [(0, 0.001) for _ in range(400)]  # all at one instant -> one regime
    ev = _carry_ev(bars, resamples=1000)
    cert = certify_carry(ev, null_beaten=True, fragility_positive=1.0)
    assert cert.verdict == "REFUTED"
    assert next(s for c, s, _ in cert.criteria if c.startswith("C5")) == "FAIL"


def test_carry_fraction_positive_reported():
    ev = _carry_ev(_carry_bars([0.001, -0.001] * 200))
    assert ev.fraction_positive == pytest.approx(0.5)


def test_pool_carry_bars_collects_positive_funding_returns():
    # a funding_carry genome on a series with positive funding must collect it: on the neutral book
    # price PnL cancels, so (taker_fee 0) every held bar's net return is the funding credit.
    n = 200
    frame = pd.DataFrame(
        {
            "open_time": range(n),
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
            "volume": [1.0] * n,
        }
    )
    funding = pd.DataFrame({"funding_time": range(n), "rate": [0.001] * n})
    genome = Genome(
        family="funding_carry", pair="AAA/USDC", params={"window": 20, "threshold": 0.0}
    )
    bars, n_pairs = pool_carry_bars(
        genome, lambda s: frame, 0.0, [genome.pair],
        window_size=1.0, step=1.0, holdout_fraction=0.5,
        read_funding=lambda p: funding,
    )
    assert n_pairs == 1
    assert bars, "expected the carry hedge to collect funding in the holdout"
    ev = build_carry_evidence(bars, n_pairs, bars_per_year=365, seed=0, resamples=200)
    assert ev.mean_return > 0 and ev.fraction_positive > 0


def test_pool_carry_bars_no_funding_yields_flat_returns():
    # no funding attached -> the hedge never opens -> every bar returns 0 (honest "earned nothing").
    n = 200
    frame = pd.DataFrame(
        {
            "open_time": range(n),
            "open": [100.0] * n,
            "high": [100.0] * n,
            "low": [100.0] * n,
            "close": [100.0] * n,
            "volume": [1.0] * n,
        }
    )
    genome = Genome(
        family="funding_carry", pair="AAA/USDC", params={"window": 20, "threshold": 0.0}
    )
    bars, _ = pool_carry_bars(
        genome, lambda s: frame, 0.0, [genome.pair],
        window_size=1.0, step=1.0, holdout_fraction=0.5,
        read_funding=lambda p: pd.DataFrame({"funding_time": [], "rate": []}),
    )
    assert all(r == 0.0 for _, r in bars)
