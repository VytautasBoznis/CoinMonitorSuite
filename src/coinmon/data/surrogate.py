from __future__ import annotations

import math
import random
from collections.abc import Mapping

import pandas as pd

from coinmon.data.models import CANDLE_COLUMNS

# Chunk V3 — the surrogate-data null (the dearest, most definitive of the certificate's C4 nulls,
# see .claude/plans/alpha-hunt.md §V.3). V1 asks "did the winner beat a random genome?" and V2 asks
# "is the winner just market exposure?"; V3 asks the deepest question: is the 51% REAL or MINED? It
# destroys the temporal signal a strategy exploits while preserving everything else — each leg's
# return distribution, its intrabar bar shape, and the cross-leg correlation structure — then lets
# the FULL search loose on that signal-free data. Whatever certificate score the search squeezes out
# of pure noise is the bar the real winner must clear. This is the White's-Reality-Check analogue.
#
# The engine is a JOINT moving-block bootstrap of the direct legs' returns: draw ONE sequence of
# contiguous return-blocks and apply it to EVERY leg identically. Applying the same block sequence
# to all legs copies the same historical instants across all coins at once, so their co-movement at
# each surrogate bar is a real historical co-movement (correlation survives); but the blocks are
# re-ordered, so the bar-to-bar predictability a momentum/mean-reversion rule keys on is gone.
# Ratios rebuild from the surrogate legs downstream (load_candles), so no search/engine changes.


def block_bootstrap_indices(n: int, block_len: int, rng: random.Random) -> list[int]:
    """A moving circular-block bootstrap index sequence over ``range(n)``: ``ceil(n / block_len)``
    blocks, each a random start position wrapping around the end, concatenated and trimmed to
    exactly ``n``. Mirrors ``evidence.block_bootstrap_ci``'s block logic. Within-block order is kept
    (so short-range structure up to ``block_len`` survives); block ORDER is randomized (so
    longer-range temporal signal dies)."""
    if n <= 0:
        return []
    block = max(1, min(block_len, n))
    n_blocks = math.ceil(n / block)
    out: list[int] = []
    for _ in range(n_blocks):
        start = rng.randrange(n)
        out.extend((start + i) % n for i in range(block))
    return out[:n]


def surrogate_legs(
    legs: Mapping[str, pd.DataFrame], *, block_len: int = 20, seed: int = 0
) -> dict[str, pd.DataFrame]:
    """Joint moving-block bootstrap of the direct ``legs`` (``BASE/QUOTE`` frames) — the V3 null's
    signal-destroying transform. Aligns every leg on its shared ``open_time``, draws ONE block index
    sequence over the aligned bars' returns, and applies it to ALL legs identically. Each surrogate
    bar takes its source bar's close-to-close return and intrabar OHLC geometry (open/high/low as
    ratios to that bar's own close, plus its volume); ``close`` is rebuilt by compounding the
    resampled returns from each leg's true first close, and the ORIGINAL calendar ``open_time`` is
    preserved so the window/regime geometry downstream is unchanged. Legs are inner-joined on time,
    so a leg only contributes over the span all legs share (the honest domain for a JOINT resample).
    Fewer than 2 shared bars -> the legs pass through unchanged."""
    frames = {sym: f.sort_values("open_time").reset_index(drop=True) for sym, f in legs.items()}
    common: set | None = None
    for f in frames.values():
        times = set(f["open_time"])
        common = times if common is None else (common & times)
    times = sorted(common) if common else []
    if len(times) < 2:
        return {sym: f.copy() for sym, f in frames.items()}

    # One block sequence over the aligned bars' returns (growth[k] = close[k+1] / close[k]), applied
    # to every leg — this is what makes the resample JOINT and preserves cross-leg correlation.
    index_seq = block_bootstrap_indices(len(times) - 1, block_len, random.Random(seed))
    out: dict[str, pd.DataFrame] = {}
    for sym, f in frames.items():
        aligned = f[f["open_time"].isin(common)].sort_values("open_time").reset_index(drop=True)
        close = aligned["close"].to_numpy(dtype=float)
        so = aligned["open"].to_numpy(dtype=float) / close  # intrabar shape: ratio to own close
        sh = aligned["high"].to_numpy(dtype=float) / close
        sl = aligned["low"].to_numpy(dtype=float) / close
        vol = aligned["volume"].to_numpy(dtype=float)
        growth = close[1:] / close[:-1]

        new_close = [float(close[0])]  # bar 0 anchors on the leg's true first close
        new_open = [float(aligned["open"].iloc[0])]
        new_high = [float(aligned["high"].iloc[0])]
        new_low = [float(aligned["low"].iloc[0])]
        new_vol = [float(vol[0])]
        for pos in index_seq:  # pos indexes growth (0..m-2); the shape source bar is pos + 1
            src = pos + 1
            c = new_close[-1] * float(growth[pos])
            new_close.append(c)
            new_open.append(c * float(so[src]))
            new_high.append(c * float(sh[src]))
            new_low.append(c * float(sl[src]))
            new_vol.append(float(vol[src]))
        out[sym] = pd.DataFrame(
            {
                "open_time": times,
                "open": new_open,
                "high": new_high,
                "low": new_low,
                "close": new_close,
                "volume": new_vol,
            }
        )[list(CANDLE_COLUMNS)]
    return out
