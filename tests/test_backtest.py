import pytest

# The backtest engine is implemented in build step 6; placeholders for that step.
pytestmark = pytest.mark.skip(reason="backtest engine implemented in build step 6")


def test_no_lookahead_guard():
    ...


def test_backtest_vs_buy_and_hold():
    ...
