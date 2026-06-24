# Learning Roadmap

A focused curriculum to be more useful on CoinMonitorSuite. Assumes strong IT/dev
background (10+ yrs: development, networking, security, diagnostics, rescue work) and
**limited quant/finance math**. Ranked by leverage for *this* project, not a generic
finance syllabus.

**Core reframe:** most of a quant *engineer's* skillset you already have — backtest infra
is distributed-systems + data-pipeline work, the fragility harness is chaos engineering,
and "don't fool yourself with your test set" is the adversarial/security mindset applied to
statistics. The gap is a specific, learnable slice of **statistics + market mechanics**.

**Skip entirely:** options pricing / Black-Scholes / stochastic calculus (options were cut),
deep econometrics, HFT / co-location, most "technical analysis" folklore.

---

## Tier 0 — The statistics of not fooling yourself (highest leverage)

The whole rig-as-product approach lives or dies here. A GA without this is a
random-garbage generator with extra steps.

- [ ] Overfitting / data-snooping / multiple-hypothesis testing — why testing N strategies
      guarantees a noise "winner" (the central risk of the GA idea)
- [ ] Out-of-sample discipline for **time series**: train/validate/test, walk-forward
- [ ] Why naive k-fold leaks the future → **purged k-fold + embargo**
- [ ] **Deflated Sharpe** & **probability of backtest overfitting** (discount a result by how
      many things you tried)
- [ ] Stationarity, and why price isn't stationary (and why a ratio might be more so)

*Transfers:* adversarial thinking / distrusting your own logs → distrusting your own backtest.
*Resource:* López de Prado, *Advances in Financial Machine Learning* (skim Tier-0 + CV
chapters). Start with the free papers "The Probability of Backtest Overfitting" and
"Deflated Sharpe Ratio."

## Tier 1 — Market microstructure & execution reality

Where the networking/diagnostics brain has the biggest edge: treat the exchange as a
distributed system with latency, partial failures, rate limits, and no atomicity.

- [ ] Order book, bid/ask spread, depth; market vs limit vs post-only; **maker vs taker** fees
- [ ] Slippage, partial fills, latency (everything the black-box `ExecutionModel` simulates)
- [ ] Bybit specifics: fee tiers, rate limits, candle/data quirks, REST vs websocket
- [ ] (Later, for perps) funding rate & basis mechanics

*Transfers:* latency modeling, retries, idempotency, failure injection = chaos engineering.
*Resource:* Bybit API docs + ccxt docs directly; execution-cost chapters of Chan (below).

## Tier 2 — Enough trading literacy to design fitness functions

Not to *invent* strategies (search does that) — to read them and define what "good" means.

- [ ] Risk/return metrics: max drawdown, Calmar, Sortino, profit factor, win-rate vs payoff
- [ ] Why Sharpe lies on fat-tailed crypto returns
- [ ] Position sizing & the **Kelly criterion** (and why fractional)
- [ ] Mean-reversion vs trend regimes
- [ ] Cointegration / pairs-trading toolkit: ADF test, Engle-Granger, **half-life of mean
      reversion**, Ornstein-Uhlenbeck (the literal math behind the ETH/BTC ratio thesis)
- [ ] What EMA / RSI actually measure and their lag tradeoffs

*Resource:* **Ernest Chan, *Algorithmic Trading: Winning Strategies and Their Rationale*** —
best starting book overall; practical, covers pairs trading / cointegration / half-life.

## Tier 3 — Evolutionary / ML layer (north star, far future)

Only after Tiers 0–2; the failure modes compound.

- [ ] Genetic programming basics: fitness design, **bloat / parsimony pressure**, why naive
      GA overfits catastrophically
- [ ] Multi-objective optimization (e.g. NSGA-II) — fitness = profit *and* robustness *and*
      simplicity, not profit alone
- [ ] Combinatorially purged cross-validation for evaluating many strategies (back to Tier 0)

*Resource:* Stefan Jansen, *Machine Learning for Algorithmic Trading* (treat GA/RL parts as
"later"; keep Tier-0 alarm bells loud).

---

## Suggested order

1. **Chan (Tier 2)** — vocabulary + cointegration math behind your own thesis (~2 weeks, fun)
2. **López de Prado papers (Tier 0)** — the anti-overfitting mindset shift
3. **Bybit/ccxt docs + microstructure (Tier 1)** — fast, given the background
4. **GP/ML (Tier 3)** — only when Phases 1–1.5 are real code

## The one habit that matters most

Treat every promising backtest like a "fix" that passed only the single test you wrote:
**assume it's wrong until it survives out-of-sample, fragility, and forward paper-trading.**
The search will produce thousands of convincing liars; your job is to be the unfoolable
reviewer. That's a security mindset — and it's the most valuable thing you bring.
