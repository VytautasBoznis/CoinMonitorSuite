from __future__ import annotations

import argparse


def _fetch_data(args: argparse.Namespace) -> None:
    raise NotImplementedError("coinmon fetch-data — build step 2")


def _backtest(args: argparse.Namespace) -> None:
    raise NotImplementedError("coinmon backtest — build step 6")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coinmon", description="CoinMonitorSuite backtester")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch-data", help="Fetch Bybit candles into the local Parquet store")
    p_fetch.add_argument("--symbol", required=True, help="e.g. BTC/USDC")
    p_fetch.add_argument("--timeframe", default="1h")
    p_fetch.add_argument("--days", type=int, default=90)
    p_fetch.set_defaults(func=_fetch_data)

    p_bt = sub.add_parser("backtest", help="Run a strategy over stored candles")
    p_bt.add_argument("--strategy", required=True, help="e.g. ema_crossover")
    p_bt.add_argument("--symbol", required=True, help="e.g. BTC/USDC, or ETH/BTC (synthetic ratio)")
    p_bt.add_argument("--timeframe", default="1h")
    p_bt.set_defaults(func=_backtest)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
