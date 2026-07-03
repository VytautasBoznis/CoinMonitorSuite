---
name: plan-c-onchain-ideation
description: "Plan C IDEATION ONLY (2026-07-03, parked behind Plan B): on-chain/DEX hunt — detect insider accumulation before CEX listings (supply drying up in pools, transfers to CEX custody wallets); needs a fat-tail certificate variant + a hard pre-trade exit-depth gate; own-DEX idea examined and rejected (venue ≠ liquidity, MiCA exposure, negative EV)"
metadata:
  node_type: memory
  type: project
---

Status: **ideation, not a plan.** Explicitly the labeled moonshot, gated behind Plan A (alpha-hunt
T–Y) and Plan B ([[plan-b-fallback-probes]]). Never promote without the user deciding; no urgency
either — the chain IS the archive, so unlike CEX collectors there is no expiring-lookback pressure
to start collecting.

**Core hypothesis (user's):** capacity-gated corners institutions can't profitably enter = DEX
microcaps. Specific signal: insider accumulation ahead of a big CEX listing — pool reserves
draining while price holds (absorption), holder concentration rising, fresh-wallet clusters funded
from a common source, and tokens moving to known CEX custody wallets BEFORE announcement (listings
need inventory). The listing pop is documented (historically +20–40%, decaying) and insider
pre-accumulation has real convictions (Coinbase 2022). Watching public chain data is legitimate
market research (the Nansen/Arkham business model).

**Honest failure modes (both barrels):** the counterparty is the contract author — majority base
rate of adversarial instruments (honeypots, mintable supply, taxed transfers, LP rugs); "supply
drying up" is ALSO the pre-rug / pump-group-loading signature (separating those is the whole
game); survivorship bias in dead-token datasets is extreme (need point-in-time universe
snapshots); listing events are rare (~100–200 pooled over years across CEXes — marginal for N
floors).

**Rig adaptations this space would need:**
- *Fat-tail certificate variant:* C2 win-rate is the wrong shape for lottery distributions
  (mostly zeros, occasional 10x; a 20% win rate can be hugely profitable) — expectancy/tail-aware
  criteria instead of Wilson bounds.
- *Exit-depth gate (pre-trade, mechanical):* position ≤ X% of pool reserves such that FULL exit
  impact ≤ Y%. On AMMs exit cost is deterministic (x·y=k, public reserves) so this is computable
  BEFORE entry. Rationale: positions are worth exit value through real depth, not marks; the
  "unsellable bag" failure mode must be prevented ex ante, never managed ex post. Remaining risk
  is then total-loss (rug/death), priced by the fat-tail certificate.
- *Execution model:* AMM math is MORE honest than CEX book-guessing (deterministic slippage), but
  MEV sandwiches + gas are new cost legs.

**Own-DEX idea: examined and rejected.** A venue is not liquidity — self-seeded pools mean being
your own counterparty (and exit liquidity for other bagholders); staking/yield denominated in a
dead token is worth nothing; EU/Lithuania MiCA makes a solo-operated DEX a regulated-activity
risk (FCIS is active). The surviving kernel is LP economics on EXISTING venues (fees vs
impermanent loss — measurable, certifiable) and v3-style range orders as bag-exit tooling.

**Rug accounting (agreed with user):** two deaths, two treatments. Pool exists = bag worth exit
value through real depth (extractable pennies). LP pulled = structurally ZERO (no pool, token
unswappable) — mark zero instantly, salvage nothing ("recovery" offers are the follow-up scam;
don't interact with the corpse token or airdropped "compensation" tokens — approval phishing).
Rug rate is priced EX ANTE as a -100% x P(rug) term in expectancy — a cost of business, not a
surprise. The exit-depth gate bounds slippage risk only; it cannot prevent venue deletion.
Residuals: tax-loss (Lithuania may require a disposal event — verify), hold-at-zero for rare
recovery distributions, and — the valuable one — **every rug is a labeled training example**:
public, timestamped pre-rug on-chain history. Plan C's rug-vs-listing classifier wants a corpus
of labeled rugs (own + harvested from public events, free).

**How to apply:** if Plan B also ends negative and the user wants the moonshot, start with a
probe-pack design in this space (pre-registered, like T0/Plan B), a point-in-time token universe
snapshot pipeline, the exit-depth gate as a day-one invariant, and the labeled-rug corpus as an
early data chunk (rugs are public; collection can start cheap). See
[[alpha-definition-edge-certificate]], [[no-strategy-preference]], [[user-infra-ui-plans]].
