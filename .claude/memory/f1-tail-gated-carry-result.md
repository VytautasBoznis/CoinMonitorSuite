---
name: f1-tail-gated-carry-result
description: "F1 tail-gated funding carry (2026-07-31) PASSED 5/5 frozen rules — +18.89%/yr on deployed capital vs +3.10% always-on — but a one-account book earns +8.75%/yr full-sample and only +2.47%/yr in the recent 24 months, so it still misses the live hurdle on recent regime."
metadata: 
  node_type: memory
  type: project
  originSessionId: 4520e228-25b0-4c00-a3cd-6a323fb7630d
  modified: 2026-07-31T20:37:28.072Z
---

First probe of [[fable-batch-10-probe-queue]], run 2026-07-31. Code `probes/f1_tail_gated_carry.py`,
log `runs/f1_tail_gated_carry.log`. Gate: arm the delta-neutral hedge when trailing-3 funding prints
annualize >= +30%, disarm below +10% (hysteresis), 58 bybit perps, 2020-03 -> 2026-07.

**FROZEN RULE: PASS 5/5.** R1 yield on deployed +18.89%/yr (need >=8%); R2 51 symbols (>=10);
R3 302 episodes (>=5); R4 top-2 episodes 9.7% of PnL (<70%); R5 6/7 calendar years positive (>=2).
**The gate genuinely works: +18.89%/yr gated vs +3.10%/yr always-on on the same universe/fees** — a
~6x lift in return per unit of deployed capital. Concentration was the expected failure mode and it
came nowhere close (9.7% vs a 70% bar).

**BUT the account-level number is the one the hurdle judges** ([[live-yield-hurdle]]):
- One equal-weight account (capital split across whatever is armed, cash otherwise): **+8.75%/yr**
  full-sample, invested 55.9% of days. Clears 5%.
- **Recent 24 months (2024-07 -> 2026-07): +2.47%/yr — MISSES the 5% hurdle.** By year: 2021 +32.3%,
  2024 +7.8%, 2025 +1.5%, 2026 +0.09% (invested only 11.5% of days). The premium is decaying, same
  disease that parked [[w3-carry-first-live-diagnosis]] — though ~13x better than W3's ~0.18%/yr.

**THE KEY STRUCTURAL FINDING (diagnostic D-C):** raising the arm threshold monotonically raises
yield-on-deployed (30% -> +18.9%/yr, 60% -> +43.9%, 100% -> +64.5%, 200% -> **+102.9%/yr**) while
the one-account calendar yield FALLS (8.75% -> 6.90% -> 6.47% -> 5.44%), because harder gates sit in
cash more (55.9% -> 8.9% of days invested). So "amputate the boring 95%" is half right: it hugely
improves capital efficiency but idle cash eats the account-level gain. **Implication: the tail gate
is best used as a capital-light OVERLAY sharing an account with something else, not as a standalone
book.** At a 200% arm it earns ~103%/yr on capital while committed only 8.9% of days.

**Caveats stated in the probe's pre-registered docstring, still open:** basis PnL is UNMODELLED (one
candle series per coin, not spot AND perp; the omission likely flatters, since we enter at a wide
premium and exit compressed); survivorship (0 delistings in the DB); funding data ends 2026-07-02.
A PASS licenses basis modelling + live-paper, NOT deployment.

Also note the gate is looser than "tail" implies: bybit baseline funding is 0.01%/8h ~= 11%/yr, so a
30%/yr arm is only ~2.7x baseline, and some "episodes" run 200+ days (the whole 2021 bull).
