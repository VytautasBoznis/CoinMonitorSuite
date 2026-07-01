"""T0 probe H1 — cross-coin relative momentum on ratio pairs (pre-registered, alpha-hunt.md §1.5).

Frozen rule (2026-07-02, before first run): FIXED params lookback=30, skip=1, band=0 —
never tuned. PASS if median OOS return > 0 on >= 4 of the 8 chunk-A series AND the pooled
positive-fold share across all series' folds > 50%. Scoring = `evaluate_fitness`
(4 folds, embargo 5), the exact chunk-A methodology.

The strategy here is a self-contained minimal version; the real `ratio_momentum` FAMILY
(searchable genes + tests) lands in chunk W1 only if this passes.

Run:  COINMON_DB_DSN=postgresql://coinmon:coinmon@localhost:5433/coinmon \
      .venv/Scripts/python probes/h1_ratio_momentum.py
"""
from __future__ import annotations

from coinmon.backtest.fitness import evaluate_fitness
from coinmon.config import settings
from coinmon.data import db
from coinmon.data.candles import load_candles
from coinmon.feed import BarView
from coinmon.strategies.base import Strategy

# The same 8 daily series chunk A scored (docs/lessons-learned.md, multi-pair run).
SERIES = [
    "XRP/ETH", "XRP/BTC", "BTC/USDC", "SOL/ETH",
    "ETH/BTC", "SOL/BTC", "ETH/USDC", "BNB/BTC",
]
LOOKBACK, SKIP, BAND = 30, 1, 0.0  # frozen; textbook momentum defaults
FOLDS, EMBARGO = 4, 5


class RatioMomentum(Strategy):
    """Long when the close outperformed itself ``LOOKBACK`` bars ago (skipping the most
    recent ``SKIP`` bars, the standard short-term-reversal guard), flat otherwise. On a
    synthetic ratio this is relative momentum between the two coins."""

    def __init__(self, lookback: int = LOOKBACK, skip: int = SKIP, band: float = BAND) -> None:
        self.lookback, self.skip, self.band = lookback, skip, band
        self._closes: list[float] = []

    def on_bar(self, view: BarView) -> int:
        self._closes.append(view.candle.close)
        need = self.lookback + self.skip + 1
        if len(self._closes) < need:
            return 0
        recent = self._closes[-1 - self.skip]
        past = self._closes[-1 - self.skip - self.lookback]
        roc = recent / past - 1.0
        return 1 if roc > self.band else 0


def main() -> None:
    conn = db.connect()
    read = lambda symbol: db.read_candles(conn, settings.exchange, symbol, "1d")  # noqa: E731

    print(f"fixed genome: lookback={LOOKBACK} skip={SKIP} band={BAND} "
          f"(folds={FOLDS}, embargo={EMBARGO}, taker={settings.taker_fee})")
    print(f"{'series':<10}{'bars':>6}{'median OOS':>12}{'mean OOS':>10}{'trades':>8}  per-fold")
    positive_medians = 0
    pooled_folds: list[float] = []
    for symbol in SERIES:
        candles = load_candles(read, symbol)
        result = evaluate_fitness(
            candles, RatioMomentum, settings.taker_fee, folds=FOLDS, embargo_bars=EMBARGO
        )
        pooled_folds.extend(result.fold_returns)
        positive_medians += result.median_oos_return > 0
        folds = ", ".join(f"{r:+.1%}" for r in result.fold_returns)
        print(f"{symbol:<10}{len(candles):>6}{result.median_oos_return:>12.2%}"
              f"{result.mean_oos_return:>10.2%}{result.total_trades:>8}  [{folds}]")
    conn.close()

    share = sum(r > 0 for r in pooled_folds) / len(pooled_folds)
    print(f"\nseries with positive median OOS: {positive_medians}/8 (need >=4)")
    print(f"pooled positive-fold share: {share:.0%} of {len(pooled_folds)} folds (need >50%)")
    verdict = "PASS" if positive_medians >= 4 and share > 0.5 else "FAIL"
    print(f"H1 VERDICT: {verdict}")


if __name__ == "__main__":
    main()
