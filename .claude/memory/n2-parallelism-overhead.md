---
name: n2-parallelism-overhead
description: "N2 multiprocessing works and is bit-identical to serial, but after N1 made genomes cheap the spawn+IPC overhead means parallel only pays off at HEAVY scale (default stays serial)"
metadata:
  type: project
---

Chunk N2 (CPU multiprocessing for the GA fitness map) landed and is correct — `workers>1` is
**bit-identical to serial** (order-preserving `ProcessPoolExecutor.map`, RNG stream stays serial in
the parent, proven by a real-spawn test). But the perf result is counter-intuitive and load-bearing
for what to do next:

**After [[build-roadmap]]'s N1 (O(n²)→O(n) incremental indicators), a single genome backtest is so
cheap that Windows process spawn + IPC + candle-dict shipping costs MORE than the compute it saves
at today's scale.** Measured on 12 cores:
- Small/daily scale (1500 bars, pop 40, gens 8, 4 folds): parallel ~**0.4×** (slower than serial).
- Heavy scale (6000 bars, pop 80, gens 12, 8 folds): parallel **2.61×** faster, identical results.

Sub-linear (never ~12×) because of three structural ceilings: (1) Windows = spawn, so each worker
re-imports pandas/coinmon (~1s fixed); (2) a **per-generation serial barrier** — the RNG-driven
selection between generations idles all workers; (3) fitness memoization shrinks the actually-
parallelizable set each generation.

**Why / how to apply:** the default is and should stay `workers=1` — don't reach for `--workers`
on routine daily-bar searches, it'll be slower. The parallel win is real but reserved for the
heavy regimes the roadmap is heading into: **N4 (universe ~12→~100 pairs)** and **Q (tree-GP, where
genomes are genuinely expensive)**. The infrastructure is in place so those chunks just flip the
flag. If we ever want a bigger speedup at moderate scale, the lever is killing the per-generation
barrier (e.g. async/steady-state GA) or a persistent pool that avoids re-spawn — NOT more cores.
Relates to [[search-overfits-not-strategy]] (scale carefully) and [[deployment-target-k8s]] (prod
HW is a separate test rig the user will buy for N4-scale).
