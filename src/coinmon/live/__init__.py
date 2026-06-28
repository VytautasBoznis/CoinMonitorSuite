"""Chunk F: forward-running infrastructure. Drive a graduated strategy bar-by-bar off the
scraper's growing TimescaleDB, reusing the backtest engine's execution core so a forward
replay reproduces the backtest exactly (parity). Read-only market data; places no orders."""
