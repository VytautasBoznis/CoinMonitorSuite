---
name: mission-find-edge-ship-ui
description: "THE MISSION (user directive 2026-07-04, updated 2026-07-05, read FIRST): find working strategies → build UI → confirmed/auto trading. UI is GATED on ≥3 winner strategies (do not start UI with fewer). Plan B is ACTIVE (calibrated negative fired). Micro-stakes live (~$10 loss) explicitly authorized for the first promising strategy — bias to action, no more 'implemented' that does nothing"
metadata: 
  node_type: memory
  type: project
  originSessionId: 87eee45e-fd58-44ae-921e-2c58f2724952
---

User directive, 2026-07-04, after reviewing the calibrated-negative sweeps
([[certified-sweep-calibrated-negative]]) and discovering the GA was a parameter tuner rather
than the composition engine they intended. This file is the priority order; read it before
picking any chunk.

**The loop:**
1. **Find a working strategy.** The GA is PARKED — no more sweeps, no genome work. Candidates
   are hand-built and pushed through the full gauntlet (probe → backtest → certificate), in
   this order:
   a. **Cross-sectional momentum rotation (W5)** — rank the USDT coin universe by trailing
      return, hold top slice, weekly. Needs ZERO new data; exhaustive small config grid (all
      runs recorded, multiple-testing deflated), portfolio-level certificate vs equal-weight
      universe benchmark. Fastest falsifiable — do first.
   b. **Funding carry (W3) certify path** — market-neutral, needs its own evaluation seam
      (return-ranked graduation can never surface it); funding data + family already exist.
   c. **Plan B probes on new inputs** ([[plan-b-fallback-probes]]) — the trigger HAS FIRED;
      P1 (free, post-shock reversal / volume shock / lead-lag) and P3 (maker-cost re-runs)
      first, then P2 on collector data. **Z0 collectors (OI, long/short, basis, liquidations)
      start IMMEDIATELY on the tooled machine — lookback expires daily.**
   d. If all the above fail: web-research fresh approaches (2026-07-04 session found
      liquidation-cascade fade + stablecoin netflow as candidates), pre-register probes,
      test, repeat. [[plan-c-onchain-ideation]] stays the gated moonshot — user decision only.
2. **≥3 winner strategies BEFORE the UI, then UI + micro-stakes live.** User directive
   2026-07-05: do NOT start building the UI until at least **3 winning (certified / strong-
   gauntlet) strategies** exist. One winner is not enough to justify the UI build — keep
   hunting candidates (W5 → W3 → Plan B probes) until three clear. Then build the
   [[ui-roadmap]] research tier, then the suggestion/confirm face. **The user has given the
   explicit confirmation
   ui-roadmap requires for pulling tier-2 forward: they authorize real-money testing at
   ~$10-loss scale as soon as a strategy is promising** (certified, or strong gauntlet
   evidence). Forward-paper and micro-live may run concurrently — seeing it act in the real
   market matters more to the user than staging purity. Execution modes graduate per
   strategy: suggest-only → auto-on-confirm (certified) → capped full-auto (paper record).
3. **Then confirmed/auto trading as the product.**

**Standing rules unchanged:** certificate thresholds never relax; probes are pre-registered;
never grow search budget to chase results; artifact-backed status reports only (the user was
burned by ~2 weeks of falsely claimed sweep progress — never say "done" without pointing at
runs/ logs or files); [[user-commits-themselves]].

The 2026-07-04 session's full memory set is ported into this repo directory: pivot directives
([[no-more-rsi-ema-permutations]], [[ga-parked]], [[ga-architecture-reality]],
[[honest-status-reporting]]), candidates ([[cross-sectional-momentum-portfolio]],
[[funding-carry-harvester]], [[order-flow-direction]], [[liquidation-cascade-fade]],
[[onchain-stablecoin-netflow]]), and methodology ([[portfolio-search-protocol]],
[[strategy-lab-model]], [[autotrading-rollout]], [[execution-plan-2026-07]],
[[machines-and-tooling]]). This repo memory is authoritative; a user-level mirror on the
user's Mac defers to it.
