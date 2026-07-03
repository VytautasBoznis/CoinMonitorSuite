from __future__ import annotations

from coinmon.data.adapters.ccxt_spot import CCXTSpotAdapter


class BinanceAdapter(CCXTSpotAdapter):
    """Binance spot candle fetcher via ccxt — BACKTEST HISTORY ONLY, never a trade venue.

    Binance's deep 2017+ history lives on USDT pairs, so it supplies the long training data
    the Edge Certificate needs while trading stays Bybit/USDC ([[train-usdt-certify-usdc]]).
    Same generic ccxt spot body as Bybit; only the exchange id differs.
    """

    name = "binance"
    _exchange_id = "binance"
