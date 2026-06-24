from coinmon.cli import build_parser
from coinmon.config import settings
from coinmon.data.models import CANDLE_COLUMNS


def test_quote_currency_is_usdc():
    # Hard constraint: the quote currency must never be USDT (EU/MiCA).
    assert settings.quote_currency == "USDC"


def test_candle_contract_columns():
    assert CANDLE_COLUMNS[0] == "open_time"
    assert set(CANDLE_COLUMNS) >= {"open", "high", "low", "close", "volume"}


def test_cli_parser_builds():
    parser = build_parser()
    args = parser.parse_args(["backtest", "--strategy", "ema_crossover", "--symbol", "BTC/USDC"])
    assert args.symbol == "BTC/USDC"
    assert args.strategy == "ema_crossover"
