---
name: first-live-combo-cross-pair-sweep
description: "First live big sweep WITH the chunk-P combo family + chunk-O cross-pair tagger: combo is competitive and produced a GO, the gate held against the bigger surface, but ALL 4 GOs tagged SPECIALIST (0 golden) — no structural edge, only crash-shorts on one down-regime"
metadata: 
  node_type: memory
  type: project
  originSessionId: 6228a1b7-55e8-4106-a7b7-2c7e61920b0e
---

First live big sweep after chunk P (2026-06-28). Config: `sweep --timeframe 1d --population 50
--generations 20 --seeds 12 --holdout 0.2 --stress 100 --cross-pair 5 --min-trades 20
--graduate-min-trades 15`. 15-pair universe (5 USDC bases: BNB/BTC/ETH/SOL/XRP → 5 direct + 10
ratios), 4 families now incl. the new `indicator_combo`. ~16s/seed serial (N1 made it cheap),
~2.5 min total. Holdout span ~330 bars; B&H was −48% (BTC) / −57% (ETH) over it = ONE down-regime.

**Result: 4/12 GO (seeds 0,2,4,9), ALL tagged SPECIALIST — 0 golden.** This is the FIRST live run
of the chunk-O cross-pair tagger, and its verdict is clean: NO structural edge in this data — every
winner is a pair-tailored curve-fit that does NOT generalize across decorrelated peers. Most GOs are
regime-adaptive leveraged PERP CRASH-SHORTS riding the BTC/ETH drop (e.g. seed 0: ema_crossover
ETH/USDC 2.1x +54.9% vs B&H −57.4%, held 0/5 peers).

**Chunk P (the combo family) validated live:**
- COMPETITIVE — won 4/12 seeds (3,5,9,10) against the three hand-built templates.
- Produced a GO (seed 9): the rule the MACHINE composed was `macd_hist(20) > -0.0077 AND rsi(2) >
  13.75`, regime-adaptive 1.4x perp, 50% stop, on BTC/SOL → +30.2%, **33 holdout trades** (the most
  of any GO = strongest evidence), fragility 100%. It came CLOSEST to golden: held on 2/5 peers
  (passed ETH/SOL +11%, BTC/XRP +9%; just missed BNB/ETH at +36.6% but 14 trades, one under the
  15-trade floor; failed BTC/USDC/SOL/XRP which crashed). So combo alpha is borderline, not golden.

**The chunk-P VERIFY question is answered: the O-hardened gate HELD against the bigger surface.**
No flood of false golden GOs — the combo's GO was tagged specialist like the rest, and thin-trade
combos were correctly NO-GO'd (seed 3 −5.9% frag 0%, seed 5 −19.6%/1 trade, seed 10 +19.3%/7
trades < 15). The N3 15-trade floor kept killing high-return lottery winners across ALL families
(seed 1 +94%/4 trades, seed 11 +16.9%/4 → NO-GO). So P earned a tentative right to go toward Q —
but see the caveat.

**Caveat (unchanged from every prior sweep):** one down-regime holdout means GOs are crash-shorts;
0 golden says none generalize. Durable alpha still UNPROVEN. To make cross-pair meaningful we need
more scraped bases (only ~14 non-own candidates, majors correlated) and a holdout that spans an
UP-regime too. The judge is trustworthy; the data can't yet show structural alpha. See
[[chunk-p-bounded-combo]], [[chunk-o-cross-pair-robustness]], [[n6-multiseed-sweep-convergence]],
[[regime-adaptive-multiseed-sweep]], [[search-overfits-not-strategy]].
